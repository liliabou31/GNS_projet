import json
import os

JSON_FILE = "routers.json"
data = {}

AS_X, AS_Y, AS_Z= 10, 20, 30
AS_IGP = {AS_X: "RIP", AS_Y: "OSPF", AS_Z:"RIP"}

link_counter = {AS_X: 1, AS_Y: 1, AS_Z: 1, "EBGP": 1}
internal_assignments = {}
ebgp_assignments = {}

def generate_router(router_num, as_number, ibgp_peers=None, ebgp_peers=None):
    global link_counter
    if ibgp_peers is None: ibgp_peers = []
    if ebgp_peers is None: ebgp_peers = []

    name = f"R{router_num}"
    igp = AS_IGP.get(as_number, "RIP")
    rid_prefix = 1 if as_number == AS_X else (2 if as_number == AS_Y else 3)
    router_id_bgp = f"{rid_prefix}.1.1.{router_num}"
    loopback = f"2001:192:100:255::{router_num}/128"

    router = {
        "name": name,
        "as_number": as_number,
        "router_id_bgp": router_id_bgp,
        "loopback": loopback,
        "interfaces": [],
        "routing": {
            "igp": igp,
            "ibgp_peers": [f"R{p}" for p in ibgp_peers],
            "ebgp_peers": []
        }
    }

    # --- Interfaces Internes ---
    for peer in ibgp_peers:
        peer_name = f"R{peer}"
        link_key = tuple(sorted([name, f"R{peer}"]))
        if link_key not in internal_assignments:
            sid = link_counter[as_number]
            if as_number == AS_X:
                pref = "168"
            elif as_number == AS_Y:
                pref = "169"
            else:
                pref = "171"
            internal_assignments[link_key] = f"2001:192:{pref}:{sid}::"
            link_counter[as_number] += 1
        
        subnet = internal_assignments[link_key]
        local_ip = f"{subnet}1/64" if name < peer_name else f"{subnet}2/64"
        peer_ip = f"{subnet}2/64" if name < peer_name else f"{subnet}1/64"
        router["interfaces"].append({"peer": peer_name, "local_ip": local_ip, "peer_ip": peer_ip, "type": "internal"})

# --- Interfaces eBGP ---
    for peer in ebgp_peers:
        peer_name = f"R{peer['peer']}"
        link_key = tuple(sorted([name, peer_name]))
        
        # 1. Gestion du subnet (une seule fois)
        if link_key not in ebgp_assignments:
            sid = link_counter["EBGP"]
            ebgp_assignments[link_key] = f"2001:192:170:{sid}::"
            link_counter["EBGP"] += 1
        
        subnet = ebgp_assignments[link_key]
        local_ip = f"{subnet}1/64" if name < peer_name else f"{subnet}2/64"
        peer_ip = f"{subnet}2/64" if name < peer_name else f"{subnet}1/64"
        
        # 2. Ajout de l'interface physique 
        router["interfaces"].append({
            "peer": peer_name, 
            "local_ip": local_ip, 
            "peer_ip": peer_ip, 
            "type": "ebgp"
        })
        
        # 3. Ajout du voisin BGP avec sa relation (UNE SEULE FOIS)
        router["routing"]["ebgp_peers"].append({
            "peer": peer_name, 
            "peer_as": peer["peer_as"],
            "relation": peer.get("relation", "provider")
        })

    # FIN DE LA FONCTION : On enregistre le routeur dans le dictionnaire global
    data[name] = router

# --- Appels de configuration ---
generate_router(1, AS_X, ibgp_peers=[2,3,5])
generate_router(2, AS_X, ibgp_peers=[1,3,4,5])
generate_router(3, AS_X, ibgp_peers=[1,2,5])
generate_router(4, AS_X, ibgp_peers=[2,5,6,7])
generate_router(5, AS_X, ibgp_peers=[1,2,3,4,6,7]) #Router Reflector 
generate_router(6, AS_X, ibgp_peers=[4,5], ebgp_peers=[{"peer": 9, "peer_as": AS_Y, "relation": "provider"},{"peer": 16, "peer_as": AS_Z, "relation": "peer"}])
generate_router(7, AS_X, ibgp_peers=[4,5], ebgp_peers=[{"peer": 8, "peer_as": AS_Y, "relation": "provider"}])

generate_router(8, AS_Y, ibgp_peers=[10,11], ebgp_peers=[{"peer": 7, "peer_as": AS_X, "relation": "customer"}])
generate_router(9, AS_Y, ibgp_peers=[10,11], ebgp_peers=[{"peer": 6, "peer_as": AS_X, "relation": "customer"},{"peer": 18, "peer_as": AS_Z, "relation": "customer"}]) 
generate_router(10, AS_Y, ibgp_peers=[8,9,11,12,13,14]) # Router Reflector
generate_router(11, AS_Y, ibgp_peers=[8,9,10,13])
generate_router(12, AS_Y, ibgp_peers=[10,13,14])
generate_router(13, AS_Y, ibgp_peers=[10,11,12,14])
generate_router(14, AS_Y, ibgp_peers=[10,12,13])

generate_router(15, AS_Z, ibgp_peers=[16,17])
generate_router(16, AS_Z, ibgp_peers=[15,17,18], ebgp_peers=[{"peer": 6, "peer_as": AS_X, "relation": "peer"}]) 
generate_router(17, AS_Z, ibgp_peers=[15,16,19])
generate_router(18, AS_Z, ibgp_peers=[15,16,17,19,20], ebgp_peers=[{"peer": 7, "peer_as": AS_X, "relation": "provider"}])
generate_router(19, AS_Z, ibgp_peers=[17,18,20])
generate_router(20, AS_Z, ibgp_peers=[18,19])

with open(JSON_FILE, "w") as f:
    json.dump(list(data.values()), f, indent=4)
