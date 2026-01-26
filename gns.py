import json
import os

# --- CONFIGURATION ---
win_user = "lilia"
project_name = "projet_test"
PROJECT_FILE = f"/mnt/c/Users/{win_user}/GNS3/projects/{project_name}/{project_name}.gns3"
DYNAMIPS_PATH = f"/mnt/c/Users/{win_user}/GNS3/projects/{project_name}/project-files/dynamips"

OSPF_PID = 1
RIP_NAME = "RIP-ASX"

def get_real_topology():
    with open(PROJECT_FILE, 'r') as f:
        conf = json.load(f)
    nodes = {n['node_id']: n['name'] for n in conf['topology']['nodes']}
    links_db = {}
    
    def fix_if_name(name):
        name = name.lower()
        if name.startswith('f'): return name.replace('f', 'FastEthernet')
        if name.startswith('g'): return name.replace('g', 'GigabitEthernet')
        if name.startswith('gi'): return name.replace('gi', 'GigabitEthernet')
        return name

    for link in conf['topology']['links']:
        n1 = nodes[link['nodes'][0]['node_id']]
        p1 = link['nodes'][0]['label']['text']
        n2 = nodes[link['nodes'][1]['node_id']]
        p2 = link['nodes'][1]['label']['text']
        
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

# --- CHARGEMENT ---
with open("routers.json") as f:
    data = json.load(f)

real_links = get_real_topology()
uuid_mapping = map_uuids()

asbr_ips = [r["loopback"].split("/")[0] for r in data if len(r["routing"]["ebgp_peers"]) > 0]

# --- GÉNÉRATION ---
for router in data:
    name = router["name"]
    as_num = router["as_number"]
    is_asbr = len(router["routing"]["ebgp_peers"]) > 0
    if name not in uuid_mapping:
        print(f"[SKIP] {name} non trouvé")
        continue

    print(f"[CONFIG] Génération pour {name}...")
    
    with open(uuid_mapping[name], "w", newline='\r\n') as f_out:
        f_out.write(f"hostname {name}\n")
        f_out.write("ipv6 unicast-routing\n")
        f_out.write("ip bgp-community new-format\n!\n")
        # --- 1. FILTRE ICMP ---
        if is_asbr:
            f_out.write("ipv6 access-list FILTER_EXTERNAL_PING\n")
            # 1. Autorise les réponses aux pings lancés par l'ASBR lui-même
            f_out.write(" permit icmp any any echo-reply\n")
            # 2. Autorise les voisins à pinger les Loopbacks des Border (ASBR)
            for ip in asbr_ips:
                f_out.write(f" permit icmp any host {ip} echo-request\n")
            # 3. BLOQUE tout le reste des pings vers l'interne
            f_out.write(" deny icmp any any echo-request\n")
            # 4. Autorise tout le reste du trafic (BGP, OSPF, Data)
            f_out.write(" permit ipv6 any any\n")
            f_out.write("!\n")

        # --- 2. LOOPBACK ---
        f_out.write("interface Loopback0\n")
        f_out.write(f" ipv6 address {router['loopback']}\n")
        if router["routing"]["igp"] == "RIP":
            f_out.write(f" ipv6 rip {RIP_NAME} enable\n")
        elif router["routing"]["igp"] == "OSPF":
            f_out.write(f" ipv6 ospf {OSPF_PID} area 0\n")
        f_out.write("!\n")

        # --- 3. INTERFACES PHYSIQUES ---
        for iface_json in router["interfaces"]:
            peer_name = iface_json["peer"]
            if name in real_links and peer_name in real_links[name]:
                real_if_name = real_links[name][peer_name]
                f_out.write(f"interface {real_if_name}\n")
                f_out.write(" no ip address\n ipv6 enable\n")
                f_out.write(f" ipv6 address {iface_json['local_ip']}\n")
                if iface_json.get("type") == "ebgp":
                    f_out.write(" ipv6 traffic-filter BLOCK_EXTERNAL_PING in\n")
                
                f_out.write(" no shutdown\n")
                if iface_json.get("type") == "internal":
                    if router["routing"]["igp"] == "RIP":
                        f_out.write(f" ipv6 rip {RIP_NAME} enable\n")
                    elif router["routing"]["igp"] == "OSPF":
                        f_out.write(f" ipv6 ospf {OSPF_PID} area 0\n")
                f_out.write("!\n")

        # --- 4. PROCESSUS IGP ---
        if router["routing"]["igp"] == "OSPF":
            f_out.write(f"ipv6 router ospf {OSPF_PID}\n router-id {router['router_id_bgp']}\nexit\n!\n")
        elif router["routing"]["igp"] == "RIP":
            f_out.write(f"ipv6 router rip {RIP_NAME}\nexit\n!\n")

        # --- 5. POLITIQUES BGP (COMMUNITIES) ---
        f_out.write("ip as-path access-list 1 permit ^$\n")
        f_out.write(f"ip community-list standard CLIENT_ONLY permit {as_num}:1\n!\n")

        f_out.write(f"route-map FROM_CLIENT permit 10\n set community {as_num}:200\n set local-preference 200\n!\n")
        f_out.write(f"route-map FROM_PROV permit 10\n set community {as_num}:100\n set local-preference 100\n!\n")
        f_out.write(f"route-map FROM_PEER permit 10\n set community {as_num}:150\n set local-preference 150\n!\n")

        f_out.write("route-map TO_PROVIDER permit 10\n match community CLIENT_ONLY\n") #allow only my client's and my as' routes to be shared
        f_out.write("route-map TO_PROVIDER permit 20\n match as-path 1\n!\n")
        
        f_out.write("route-map TO_PEER permit 10\n match community CLIENT_ONLY\n") #idem
        f_out.write("route-map TO_PEER permit 20\n match as-path 1\n!\n")

        f_out.write("route-map TO_CLIENT permit 10\n!\n") #all my routes are shared (cause i'm getting payed)

        # --- PREFIX-LIST : autoriser uniquement les ASBR ---
        asbr_list = [r["loopback"].split("/")[0] for r in data if len(r["routing"]["ebgp_peers"]) > 0]

        f_out.write("ipv6 prefix-list PL-ASBR\n")
        for i, lb in enumerate(asbr_list, start=5):
            f_out.write(f" seq {i} permit {lb}\n")
        f_out.write("!\n")

        f_out.write("route-map FROM_PROVIDER_FILTER permit 10\n")
        f_out.write(" match ipv6 address prefix-list PL-ASBR\n")
        f_out.write("!\n")
        
        # --- 6. PROCESSUS BGP ---
        f_out.write(f"router bgp {as_num}\n")
        f_out.write(f" bgp router-id {router['router_id_bgp']}\n")
        f_out.write(" bgp timers 5 15\n")
        f_out.write(" no bgp default ipv4-unicast\n")

        # Définition Voisins IBGP
        for peer in router["routing"]["ibgp_peers"]:
            p_ip = next(x["loopback"] for x in data if x["name"] == peer).split('/')[0]
            f_out.write(f" neighbor {p_ip} remote-as {as_num}\n")
            f_out.write(f" neighbor {p_ip} update-source Loopback0\n")

        # Définition Voisins EBGP
        for e_peer in router["routing"]["ebgp_peers"]:
            iface = next(i for i in router["interfaces"] if i["peer"] == e_peer["peer"])
            p_ip_ebgp = iface["peer_ip"].split("/")[0]
            f_out.write(f" neighbor {p_ip_ebgp} remote-as {e_peer['peer_as']}\n")

        # --- 7. ADDRESS-FAMILY IPV6 ---
        f_out.write(" address-family ipv6 unicast\n")
        
        for peer in router["routing"]["ibgp_peers"]:
            p_ip = next(x["loopback"] for x in data if x["name"] == peer).split('/')[0]
            f_out.write(f"  neighbor {p_ip} activate\n")
            if router["name"] in ["R5", "R10", "R18"]:
                f_out.write(f"  neighbor {p_ip} route-reflector-client\n")
            f_out.write(f"  neighbor {p_ip} send-community both\n")
            if len(router["routing"]["ebgp_peers"]) > 0:
                f_out.write(f"  neighbor {p_ip} next-hop-self\n")

        for e_peer in router["routing"]["ebgp_peers"]:
            iface = next(i for i in router["interfaces"] if i["peer"] == e_peer["peer"])
            p_ip_ebgp = iface["peer_ip"].split("/")[0]
            rel = e_peer["relation"]
            
            f_out.write(f"  neighbor {p_ip_ebgp} activate\n")
            f_out.write(f"  neighbor {p_ip_ebgp} send-community\n")
            
            if rel == "customer":
                f_out.write(f"  neighbor {p_ip_ebgp} route-map FROM_CLIENT in\n")
                f_out.write(f"  neighbor {p_ip_ebgp} route-map TO_CLIENT out\n")
            elif rel == "provider":
                f_out.write(f"  neighbor {p_ip_ebgp} route-map FROM_PROVIDER_FILTER in\n")
                f_out.write(f"  neighbor {p_ip_ebgp} route-map TO_PROVIDER out\n")
            elif rel == "peer":
                f_out.write(f"  neighbor {p_ip_ebgp} route-map FROM_PEER in\n")
                f_out.write(f"  neighbor {p_ip_ebgp} route-map TO_PEER out\n")

        f_out.write(f"  network {router['loopback']}\n")
        f_out.write(" exit-address-family\n!\nend\n")


print("\nDéploiement terminé.")
