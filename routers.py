import json
import os

JSON_FILE = "routers.json"
data = {}

AS_X, AS_Y = 10, 20
AS_IGP = {AS_X: "RIP", AS_Y: "OSPF"}

link_counter = {AS_X: 1, AS_Y: 1, "EBGP": 1}
internal_assignments = {}
ebgp_assignments = {}

def generate_router(router_num, as_number, ibgp_peers=None, ebgp_peers=None):
    global link_counter
    if ibgp_peers is None: ibgp_peers = []
    if ebgp_peers is None: ebgp_peers = []

    name = f"R{router_num}"
    igp = AS_IGP.get(as_number, "RIP")
    router_id_bgp = f"{1 if as_number == AS_X else 2}.1.1.{router_num}"
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
            pref = "168" if as_number == AS_X else "169"
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
        if link_key not in ebgp_assignments:
            sid = link_counter["EBGP"]
            ebgp_assignments[link_key] = f"2001:192:170:{sid}::"
            link_counter["EBGP"] += 1
        
        subnet = ebgp_assignments[link_key]
        local_ip = f"{subnet}1/64" if name < peer_name else f"{subnet}2/64"
        peer_ip = f"{subnet}2/64" if name < peer_name else f"{subnet}1/64"
        router["interfaces"].append({"peer": peer_name, "local_ip": local_ip, "peer_ip": peer_ip, "type": "ebgp"})
        router["routing"]["ebgp_peers"].append({"peer": peer_name, "peer_as": peer["peer_as"]})

    data[name] = router

# --- Appels de configuration ---
generate_router(1, AS_X, ibgp_peers=[2,3])
generate_router(2, AS_X, ibgp_peers=[1,3,4])
generate_router(3, AS_X, ibgp_peers=[1,2,5])
generate_router(4, AS_X, ibgp_peers=[2,5,7])
generate_router(5, AS_X, ibgp_peers=[3,4,6,7])
generate_router(6, AS_X, ibgp_peers=[4,5], ebgp_peers=[{"peer": 9, "peer_as": AS_Y}])
generate_router(7, AS_X, ibgp_peers=[4,5], ebgp_peers=[{"peer": 8, "peer_as": AS_Y}])

generate_router(8, AS_Y, ibgp_peers=[10,11], ebgp_peers=[{"peer": 7, "peer_as": AS_X}])
generate_router(9, AS_Y, ibgp_peers=[10,11], ebgp_peers=[{"peer": 6, "peer_as": AS_X}])
generate_router(10, AS_Y, ibgp_peers=[8,9,11,12])
generate_router(11, AS_Y, ibgp_peers=[8,9,10,13])
generate_router(12, AS_Y, ibgp_peers=[10,13,14])
generate_router(13, AS_Y, ibgp_peers=[11,12,14])
generate_router(14, AS_Y, ibgp_peers=[12,13])

with open(JSON_FILE, "w") as f:
    json.dump(list(data.values()), f, indent=4)