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
        
        # Nettoyage robuste du nom de l'interface
        def fix_if_name(name):
            name = name.lower()
            if name.startswith('f'): return name.replace('f', 'FastEthernet')
            if name.startswith('g'): return name.replace('g', 'GigabitEthernet')
            if name.startswith('gi'): return name.replace('gi', 'GigabitEthernet')
            return name

        if n1 not in links_db: links_db[n1] = {}
        if n2 not in links_db: links_db[n2] = {}
        links_db[n1][n2] = fix_if_name(p1)
        links_db[n2][n1] = fix_if_name(p2)
    return links_db

def map_uuids():
    mapping = {}
    if not os.path.exists(DYNAMIPS_PATH): return mapping
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
        f_out.write(f"hostname {name}\n")
        f_out.write("ipv6 unicast-routing\n")
        f_out.write("ip bgp-community new-format\n!\n")

        # Loopback
        f_out.write("interface Loopback0\n")
        f_out.write(f" ipv6 address {router['loopback']}\n")
        if router["routing"]["igp"] == "RIP":
            f_out.write(f" ipv6 rip {RIP_NAME} enable\n")
        elif router["routing"]["igp"] == "OSPF":
            f_out.write(f" ipv6 ospf {OSPF_PID} area 0\n")
        f_out.write("!\n")

        # Interfaces Physiques
        for iface_json in router["interfaces"]:
            peer_name = iface_json["peer"]
            if name in real_links and peer_name in real_links[name]:
                real_if_name = real_links[name][peer_name]
                f_out.write(f"interface {real_if_name}\n")
                f_out.write(" no ip address\n ipv6 enable\n")
                f_out.write(f" ipv6 address {iface_json['local_ip']}\n")
                f_out.write(" no shutdown\n")
                if iface_json.get("type") == "internal":
                    if router["routing"]["igp"] == "RIP":
                        f_out.write(f" ipv6 rip {RIP_NAME} enable\n")
                    elif router["routing"]["igp"] == "OSPF":
                        f_out.write(f" ipv6 ospf {OSPF_PID} area 0\n")
                f_out.write("!\n")

        # Processus IGP
        if router["routing"]["igp"] == "OSPF":
            f_out.write(f"ipv6 router ospf {OSPF_PID}\n router-id {router['router_id_bgp']}\nexit\n!\n")
        elif router["routing"]["igp"] == "RIP":
            f_out.write(f"ipv6 router rip {RIP_NAME}\nexit\n!\n")

        # POLITIQUES
        f_out.write("ip as-path access-list 1 permit ^$\n")
        f_out.write(f"ip community-list standard CLIENT_ONLY permit {router['as_number']}:1\n!\n") # identifie les routes des clients

        f_out.write(f"route-map FROM_CLIENT permit 10\n set community {router['as_number']}:1\n set local-preference 200\n!\n")
        f_out.write(f"route-map FROM_PROV permit 10\n set community {router['as_number']}:3\n set local-preference 100\n!\n")
        f_out.write(f"route-map FROM_PEER permit 10\n set community {router['as_number']}:2\n set local-preference 150\n!\n")

        # providers mes routes et routes de mes clients
        f_out.write("route-map TO_PROVIDER permit 10\n match community CLIENT_ONLY\n") 
        f_out.write("route-map TO_PROVIDER permit 20\n match as-path 1\n!\n")
        
        # envoie a peers mes routes et routes de mes clients
        f_out.write("route-map TO_PEER permit 10\n match community CLIENT_ONLY\n") # Est ce que cette route appartient à un de mes clients ?
        f_out.write("route-map TO_PEER permit 20\n match as-path 1\n!\n") # Est-ce que c'est ma propre route (créée par moi-même) ?
        f_out.write("route-map TO_PEER permit 30\n!\n") # Il laisse tout passer

        f_out.write("route-map TO_CLIENT permit 10\n!\n") # on envoie tout a nos clients

        # BGP
        f_out.write(f"router bgp {router['as_number']}\n")
        f_out.write(" bgp fast-external-fallover\n")
        f_out.write(f" bgp router-id {router['router_id_bgp']}\n")
        f_out.write(" bgp timers 5 15\n")
        f_out.write(" no bgp default ipv4-unicast\n")

        # Définition des voisins (Remote-AS) - Toujours en dehors de l'Address-family
        for peer in router["routing"]["ibgp_peers"]:
            p_ip = next(x["loopback"] for x in data if x["name"] == peer).split('/')[0]
            f_out.write(f" neighbor {p_ip} remote-as {router['as_number']}\n")
            f_out.write(f" neighbor {p_ip} update-source Loopback0\n")

        for e_peer in router["routing"]["ebgp_peers"]:
            iface = next(i for i in router["interfaces"] if i["peer"] == e_peer["peer"])
            p_ip_ebgp = iface["peer_ip"].split("/")[0]
            f_out.write(f" neighbor {p_ip_ebgp} remote-as {e_peer['peer_as']}\n")

        # Activation et Politiques - Toujours DANS l'Address-family
        f_out.write(" address-family ipv6 unicast\n")
        
        # Activation IBGP
        for peer in router["routing"]["ibgp_peers"]:
            p_ip = next(x["loopback"] for x in data if x["name"] == peer).split('/')[0]
            f_out.write(f"  neighbor {p_ip} activate\n")
            if router["name"] in ["R5", "R10","R18"]:
                f_out.write(f"  neighbor {p_ip} route-reflector-client\n")
            f_out.write(f"  neighbor {p_ip} send-community both\n")
            if len(router["routing"]["ebgp_peers"]) > 0:
                f_out.write(f"  neighbor {p_ip} next-hop-self\n")

        # Activation EBGP
        for e_peer in router["routing"]["ebgp_peers"]:
            iface = next(i for i in router["interfaces"] if i["peer"] == e_peer["peer"])
            p_ip_ebgp = iface["peer_ip"].split("/")[0]
            f_out.write(f"  neighbor {p_ip_ebgp} activate\n")
            f_out.write(f"  neighbor {p_ip_ebgp} send-community\n")
            
            if e_peer["relation"] == "customer":
                f_out.write(f"  neighbor {p_ip_ebgp} route-map FROM_CLIENT in\n")
                f_out.write(f"  neighbor {p_ip_ebgp} route-map TO_CLIENT out\n")
            elif e_peer["relation"] == "provider":
                f_out.write(f"  neighbor {p_ip_ebgp} route-map FROM_PROV in\n")
                f_out.write(f"  neighbor {p_ip_ebgp} route-map TO_PROVIDER out\n")
            elif e_peer["relation"] == "peer":
                f_out.write(f"  neighbor {p_ip_ebgp} route-map FROM_PEER in\n") # Réutilisé pour marquer community :1
                f_out.write(f"  neighbor {p_ip_ebgp} route-map TO_PEER out\n")

        f_out.write(f"  network {router['loopback']}\n")
        f_out.write(" exit-address-family\n!\nend\n")

print("\n[FIN] Déploiement terminé.")