# AJOUTER L'EXPLICATION DU BLOC AJOUTE SUR GNS.PY !!!!!!!

Hello,
le script routeurs.py a pour rôle de créer le fichier json / le remplir en appelant la fonction generate_routers.

le script gns-deployment est pour créer les liens rip, ospf ou ebgp entre les routeurs. 

pour ping apres entre un routeur ebgp de asX et un routeur de asY faut faire : ping 2001:192:100:255::10 source loopback 0 (2001:192:100:255::10 étant l'adresse de loopback) 

# Fonctionnement des scripts en détail

## routers.py 

### fonction generate_router(router_num, as_number, ibgp_peers=None, ebgp_peers=None) : 

__→ Génération de l'identité__ 

Chaque routeur reçoit : 
* Router-ID BGP : Basé sur l'AS number pour éviter les collisions
* Loopback IPv6 : une adresse fixe unique en /128, généré d'après cette logique : "2001:192:100:255::{router_num}/128"
* Protocole IGP (RIP ou OSPF) : séléctionné via AS_IGP 

Pour chaque voisin du routeur, la fonction génère une clé qui représente le lien entre les deux routeurs : tuple(sorted([hostname, peer]))

Si le lien est nouveau, (not in internal_assignements), la fonction va aller regarder link_counter pour l'AS concerné et génère un préfixe IPv6 unique : "2001:192:{pref}:{sid}::" 

* "pref" est un nombre fixe associé à l'AS (si as_number = AS_X, pref = 168 par exemple) 
* "sid" est déterminé avec link_counter : link_counter = {AS_X: 1, AS_Y: 1, AS_Z: 1, "EBGP": 1}, on incrémante par 1 à chaque fois qu'on attribue un "sid"

__→ Détermination de l'IP__

Pour les ibgp_peers : 
La fonction prends l'adresse du sous-réseau généré précédemment, et sur le segment donné, le routeur avec le nom le plus grand prend le suffixe "::2" et celui avec le nom le plus petit prend le suffixe "::1".
Ensuite, on ajoute au dictionnaire : peer_name, local_ip, peer_ip, et le type de lien, ici internal

Pour les ebgp_peers :
Lorsque les deux appartiennent à deux AS différents, la logique est la même que pour deux routers d'un même AS. On associe à chaque lien ebgp un identifiant unique qu'on retrouve dans link_counter["EBGP"] (on incrémente de 1 cette valeur pour les prochains liens ebgp) : "2001:192:170:{sid}::"
En plus de l'interface physique stockée dans router["interfaces"], la fonction va également stocker dans router["routing"]["ebgp_peers"] : peer, peer_as, relation (provider, peer ou customer)

Enfin, on ajoute router dans le dictionnaire global data

→ La fin du script sert à faire les appels de configuration pour chaque routeur, puis d'écrire le fichier d'intention routers.json

__→ Après chaque modifications du script, il est nécessaire de l'exécuter avant d'exécuter gns.py__


## gns.py 

### fonction get_real_topology()

Cette fonction a pour but de scanner automatiquement le schéma GNS3 pour identifier précisémeent quel routeur est connecté à quel autre et sur quel port. Cela permet de rendre le script capable de s'adapter au câblage réel fait dans GNS3.

La fonction va d'abord ouvrir le fichier routers.json, puis va créer le dictionnaire nodes pour associer l'UUID de chaque routeur à son nom lisible 
La boucle for link in conf['topology']['links'] parcours la liste topology/links et pour chaque câble trouvé, il identifie les deux routeurs aux extrémités (n1 et n2), et récupère le nom des interfaces où le câble est branché (p1 et p2). 
 
La sous-fonction fix_if_name(name) normalise le nom des interfaces. En effet, GNS3 a tendance à écrire les noms de manière abrégé (par exemple f0/0), mais pour que la configuration Cisco fonctionne, il faut écrire le nom complet des interfaces. 
Exemple : fix_if_name(f0/0) = FastEthernet0/0 ; fix_if_name(g1/0) = GigabitEthernet1/0

Enfin, la fonction remplit un dictionnaire à deux niveaux qui ressemble à ceci : 

{
  "R1": { "R2": "FastEthernet0/0", "R3": "FastEthernet1/0" },
  "R2": { "R1": "FastEthernet0/0" }
}

### map_uuids()

Cette fonction identifie l'emplacement physique des fichiers de configuration sur l'ordinateur en faisant correspondre le nom de chaque routeur à son dossier technique GNS3 (UUID).

### section CHARGEMENT DES DONNÉES

* chargement le fichier routers.json dans _data_
* stockage les branchements obtenus grâce à get_real_topology() dans _real_links_
* stockage les chemins d'accès directs aux fichiers de configuration de chaque routeur dans _uuid_mapping_

### Section GÉNÉRATION DES CONFIGS

Cette section finale a pour rôle de transformer les données logiques en fichiers .cfg prêt à être chargés par GNS3.

Tout d'abord, par précaution, le script vérifie la présece du routeur dans le projet GNS3. Ainsi, si le routeur est défini dans le code mais absent du schéma il sera ignoré. 

→ Adressage et Routage Interne (IGP)

Le script va configurer les bases de chaque équipement : Loopback et Unicast-Routing en activant l'IPv6 et la configuration de l'interface de gestion, et les interfaces physiques, en activant le protocol de routage interne correspondant (OSPF ou RIP). 

→ BGP et Politiques de Routage

Le script automatise la configuration BGP : 

* Relations commerciales : Il applique des _route-map_ (FROM_CLIENT, FROM_PROV, etc.) en gérant les priorités via le __Local_Pref__ et le marquage par les __Communities__.
* Filtrage de Transit : Implémentation des règles de filtrage pour s'assurer qu'un fournisseur ne reçoive que les routes des clients. 
* Router Reflector : Pour les RR, le script active automatiquement la fonction "route-reflector-client".

→ Automatisation du "Next-Hop-Self"

Le script applique la commande "next-hop-self" uniquement si le routeur possède des voisins eBGP. Cela garantit que les routes externes sont bien diffusées et joignables à l'intérieur de l'AS.
