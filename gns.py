import json
import os

# --- CONFIGURATION ---
win_user = "lilia"
project_name = "projet_test"
# Chemins WSL vers Windows
PROJECT_FILE = f"/mnt/c/Users/{win_user}/GNS3/projects/{project_name}/{project_name}.gns3"
DYNAMIPS_PATH = f"/mnt/c/Users/{win_user}/GNS3/projects/{project_name}/project-files/dynamips"

OSPF_PID = 1
RIP_NAME = "RIP-ASX"

def get_real_topology():
    with open(PROJECT_FILE, 'r') as f:
        conf = json.load(f)
    nodes = {n['node_id']: n['name'] for n in conf['topology']['nodes']}
    links_db = {}
    for link in conf['topology']['links']:
        n1 = nodes[link['nodes'][0]['node_id']]
        p1 = link['nodes'][0]['label']['text']
        n2 = nodes[link['nodes'][1]['node_id']]
        p2 = link['nodes'][1]['label']['text']
        
        # Nettoyage du nom de l'interface (ex: f0/0 -> FastEthernet0/0)
        def fix_if_name(name):
            if name.startswith('f'): return name.replace('f', 'FastEthernet')
            if name.startswith('g'): return name.replace('g', 'GigabitEthernet')
            if name.startswith('Gi'): return name.replace('Gi', 'GigabitEthernet')
            return name

        if n1 not in links_db: links_db[n1] = {}
        if n2 not in links_db: links_db[n2] = {}
        links_db[n1][n2] = fix_if_name(p1)
        links_db[n2][n1] = fix_if_name(p2)
    return links_db

def map_uuids():
    """ Associe le nom du routeur au chemin du fichier config sur le disque """
    mapping = {}
    for uuid_dir in os.listdir(DYNAMIPS_PATH):
        cfg_path = os.path.join(DYNAMIPS_PATH, uuid_dir, "configs")
        if os.path.isdir(cfg_path):
            for f in os.listdir(cfg_path):
                if f.endswith("_startup-config.cfg"):
                    full_p = os.path.join(cfg_path, f)
                    with open(full_p, 'r', errors='ignore') as f_in:
                        for line in f_in:
                            if line.startswith("hostname "):
                                r_name = line.split()[1].strip()
                                mapping[r_name] = full_p
    return mapping

# --- CHARGEMENT DES DONNÉES ---
with open("routers.json") as f:
    data = json.load(f)

real_links = get_real_topology()
uuid_mapping = map_uuids()

# --- GÉNÉRATION DES CONFIGS ---
for router in data:
    name = router["name"]
    if name not in uuid_mapping:
        print(f"[SKIP] {name} non trouvé dans le projet GNS3")
        continue

    print(f"[CONFIG] Génération pour {name}...")
    
    with open(uuid_mapping[name], "w", newline='\r\n') as f_out:
        # Configuration de base
        f_out.write(f"hostname {name}\nipv6 unicast-routing\n!\n")

        # Loopback
        f_out.write("interface Loopback0\n")
        f_out.write(f" ipv6 address {router['loopback']}\n")
        if router["routing"]["igp"] == "RIP":
            f_out.write(f" ipv6 rip {RIP_NAME} enable\n")
        elif router["routing"]["igp"] == "OSPF":
            f_out.write(f" ipv6 ospf {OSPF_PID} area 0\n")
        f_out.write("!\n")

        # Interfaces Physiques (Détectées via .gns3)
        for iface_json in router["interfaces"]:
            peer_name = iface_json["peer"]
            
            # On récupère le nom de l'interface physique réelle
            if name in real_links and peer_name in real_links[name]:
                real_if_name = real_links[name][peer_name]
                
                f_out.write(f"interface {real_if_name}\n")
                f_out.write(" no ip address\n ipv6 enable\n")
                f_out.write(f" ipv6 address {iface_json['local_ip']}\n")
                f_out.write(" no shutdown\n")
                
                # Activation IGP (seulement si interne)
                if iface_json.get("type") == "internal":
                    if router["routing"]["igp"] == "RIP":
                        f_out.write(f" ipv6 rip {RIP_NAME} enable\n")
                    elif router["routing"]["igp"] == "OSPF":
                        f_out.write(f" ipv6 ospf {OSPF_PID} area 0\n")
                f_out.write("!\n")
            else:
                print(f"  [!] Attention: Pas de lien physique trouvé entre {name} et {peer_name}")

        # Processus IGP
        if router["routing"]["igp"] == "OSPF":
            f_out.write(f"ipv6 router ospf {OSPF_PID}\n router-id {router['router_id_bgp']}\nexit\n!\n")
        elif router["routing"]["igp"] == "RIP":
            f_out.write(f"ipv6 router rip {RIP_NAME}\nexit\n!\n")

        # BGP
        f_out.write(f"router bgp {router['as_number']}\n")
        f_out.write(f" bgp router-id {router['router_id_bgp']}\n")
        f_out.write(" no bgp default ipv4-unicast\n")

        # 1. Définition des voisins (Remote-AS et Source)
        for peer in router["routing"]["ibgp_peers"]:
            p_ip = next(x["loopback"] for x in data if x["name"] == peer).split('/')[0]
            f_out.write(f" neighbor {p_ip} remote-as {router['as_number']}\n")
            f_out.write(f" neighbor {p_ip} update-source Loopback0\n")

        for e_peer in router["routing"]["ebgp_peers"]:
            iface = next(i for i in router["interfaces"] if i["peer"] == e_peer["peer"])
            p_ip_ebgp = iface["peer_ip"].split("/")[0]
            f_out.write(f" neighbor {p_ip_ebgp} remote-as {e_peer['peer_as']}\n")

        # 2. Activation dans l'Address-family (C'est ICI que tout se joue)
        f_out.write(" address-family ipv6 unicast\n")
        
        # Activation iBGP + Correction Next-Hop
        for peer in router["routing"]["ibgp_peers"]:
            p_ip = next(x["loopback"] for x in data if x["name"] == peer).split('/')[0]
            f_out.write(f"  neighbor {p_ip} activate\n")
            # LA COMMANDE DOIT ÊTRE ICI POUR L'IPV6
            if len(router["routing"]["ebgp_peers"]) > 0:
                f_out.write(f"  neighbor {p_ip} next-hop-self\n")

        # Activation eBGP
        for e_peer in router["routing"]["ebgp_peers"]:
            iface = next(i for i in router["interfaces"] if i["peer"] == e_peer["peer"])
            p_ip_ebgp = iface["peer_ip"].split("/")[0]
            f_out.write(f"  neighbor {p_ip_ebgp} activate\n")
        
        f_out.write(f"  network {router['loopback']}\n")
        f_out.write(" exit-address-family\n!\nend\n")

print("\n[FIN] Toutes les configurations ont été injectées dans les dossiers Windows.")