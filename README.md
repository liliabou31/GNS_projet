Hello,
le script routeurs.py a pour rôle de créer le fichier json / le remplir en appelant la fonction generate_routers.

le script gns-deployment est pour créer les liens rip, ospf ou ebgp entre les routeurs. 

pour ping apres entre un routeur ebgp de asX et un routeur de asY faut faire : ping 2001:192:100:255::10 source loopback 0 (2001:192:100:255::10 étant l'adresse de loopback) 
