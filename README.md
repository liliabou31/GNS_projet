Hello,
le script routeurs.py a pour rôle de créer le fichier json / le remplir en appelant la fonction generate_routers.

le script gns-deployment est pour créer les liens rip, ospf ou ebgp entre les routeurs. 

pour ping apres entre un routeur ebgp de asX et un routeur de asY faut faire : ping 2001:192:100:255::10 source loopback 0 (2001:192:100:255::10 étant l'adresse de loopback) 

# Fonctionnement des scripts en détail

## routers.py 

### fonction generate_router(router_num, as_number, ibgp_peers=None, ebgp_peers=None) : 

→ Génération de l'identité 

Chaque routeur reçoit : 
* Router-ID BGP : Basé sur l'AS number pour éviter les collisions
* Loopback IPv6 : une adresse fixe unique en /128, généré d'après cette logique : "2001:192:100:255::{router_num}/128"
* Protocole IGP (RIP ou OSPF) : séléctionné via AS_IGP 

Pour chaque voisin du routeur, la fonction génère une clé qui représente le lien entre les deux routeurs : tuple(sorted([hostname, peer]))

Si le lien est nouveau, (not in internal_assignements), la fonction va aller regarder link_counter pour l'AS concerné et génère un préfixe IPv6 unique : 

"2001:192:{pref}:{sid}::" 
* "pref" est un nombre fixe associé à l'AS (si as_number = AS_X, pref = 168 par exemple) 
* "sid" est déterminé avec link_counter : link_counter = {AS_X: 1, AS_Y: 1, AS_Z: 1, "EBGP": 1}, on incrémante par 1 à chaque fois qu'on attribue un "sid"

Détermination de l'IP 

Pour les ibgp_peers : 
La fonction prends l'adresse du sous-réseau généré précédemment, et sur le segment donné, le routeur avec le nom le plus grand prend le suffixe "::2" et celui avec le nom le plus petit prend le suffixe "::1".
Ensuite, on ajoute au dictionnaire : peer_name, local_ip, peer_ip, et le type de lien, ici internal

Pour les ebgp_peers :
Lorsque les deux appartiennent à deux AS différents, la logique est la même que pour deux routers d'un même AS. On associe à chaque lien ebgp un identifiant unique qu'on retrouve dans link_counter["EBGP"] (on incrémente de 1 cette valeur pour les prochains liens ebgp) : "2001:192:170:{sid}::"
En plus de l'interface physique stockée dans router["interfaces"], la fonction va également stocker dans router["routing"]["ebgp_peers"] : peer, peer_as, relation (provider, peer ou customer)

Enfin, on ajoute router dans le dictionnaire global data

→ La fin du script sert à faire les appels de configuration pour chaque routeur, puis d'écrire le fichier d'intention routers.json

## gns.py 
