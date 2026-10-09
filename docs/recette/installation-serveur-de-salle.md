# Installer le serveur de salle (Windows + Docker Desktop)

Le « serveur de salle » est l'ordinateur portable qui fait tourner QURANOVA le jour du concours, sur un Wi-Fi dédié sans Internet.
Quatre conteneurs : **PostgreSQL** (données), **Redis** (messages temps réel), **web** (Daphne, l'application), **Nginx** (porte d'entrée).

## 1. Une seule fois, avec Internet

1. Windows 10/11 à jour. Activer la virtualisation dans le BIOS si Docker le demande.
2. Installer **Docker Desktop** (https://www.docker.com/products/docker-desktop/) avec l'option **WSL 2** cochée ; redémarrer.
3. Ouvrir Docker Desktop, accepter les conditions, attendre l'icône verte. Vérifier :
   ```powershell
   docker --version
   docker compose version
   ```
4. Récupérer le projet : `git clone https://github.com/afaqsuca/quranova_v1.git` puis `git checkout claude/confident-goodall-7iqyck`.
5. Créer le fichier `.env` :
   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```
   À remplir : `DJANGO_SECRET_KEY` (≥ 50 caractères aléatoires : `python -c "import secrets; print(secrets.token_urlsafe(50))"`),
   `DB_PASSWORD`, et **`DJANGO_ALLOWED_HOSTS`** = l'adresse IP fixe du portable sur le Wi-Fi dédié (ex. `192.168.50.10`) et/ou son nom.
6. **Construire les images** (nécessite Internet, plusieurs minutes) : `.\scripts\demarrer.ps1`.
   Les images restent ensuite sur le portable : **le jour J, plus besoin d'Internet**.

## 2. Réseau du jour J

- Donner au portable une **adresse IP fixe** sur le routeur Wi-Fi dédié (réservation DHCP ou IP statique) et la reporter dans `DJANGO_ALLOWED_HOSTS`.
- **Pare-feu Windows** : autoriser le port 80 en entrée (réseau privé) :
  ```powershell
  New-NetFirewallRule -DisplayName "QURANOVA HTTP" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow -Profile Private
  ```
- Mettre le Wi-Fi en profil réseau « Privé ». Désactiver la mise en veille du portable branché sur secteur (et sur onduleur, REC-41).

## 3. Démarrer, arrêter

```powershell
.\scripts\demarrer.ps1          # démarre et affiche les adresses à saisir sur les tablettes
.\scripts\arreter.ps1           # arrête (les données sont conservées)
docker compose logs -f web      # suivre les journaux
```
Première installation seulement : `docker compose exec web python manage.py createsuperuser` (mot de passe de **12 caractères minimum**). À la première connexion, le **deuxième facteur** est activé : installer une application d'authentification sur le téléphone, scanner le QR code (sans Internet), saisir le code. Un téléphone perdu se règle par « Réinitialiser le deuxième facteur » (administrateur).
Le démarrage automatique après un redémarrage est assuré par `restart: unless-stopped` + « Démarrer Docker Desktop à l'ouverture de session ».

## 4. Sauvegardes (REC-18)

```powershell
.\scripts\sauvegarder.ps1       # une sauvegarde horodatée ; à planifier toutes les 15 min
```
Dossier choisi par `DOSSIER_SAUVEGARDES` dans `.env` (disque externe recommandé).

## 5. Reprise sur l'ordinateur de secours (REC-36, scénario E, < 15 minutes)

1. Sur le secours : Docker Desktop installé, projet cloné, `.env` identique à celui du principal (copie sur clé USB), images déjà construites.
2. Lui donner l'IP du serveur principal (ou ajouter son IP à `DJANGO_ALLOWED_HOSTS`).
3. `.\scripts\demarrer.ps1`, puis restaurer la dernière sauvegarde :
   ```powershell
   docker compose exec web python manage.py restaurer /data/sauvegardes/<fichier>.dump --vers-base quranova_restaure
   ```
   (puis pointer `DB_NAME` sur cette base, ou restaurer dans la base de travail après arrêt du service `web`).
4. Vérifier : `docker compose exec web python manage.py verifier_audit`.
5. Chronométrer et consigner dans le journal de recette.

## 6. Tests dans Docker

```powershell
.\scripts\tests-docker.ps1
```

## Dépannage

| Symptôme | Cause probable |
|---|---|
| `Docker Desktop n'est pas démarré` | lancer Docker Desktop, attendre l'icône verte |
| Page « Bad Request (400) » | l'adresse saisie n'est pas dans `DJANGO_ALLOWED_HOSTS` |
| Tablette sans réponse | pare-feu (port 80) ou mauvais profil réseau |
| `web` redémarre en boucle | `docker compose logs web` : clé secrète faible, hôtes vides ou mot de passe PostgreSQL différent de celui de la première création |
| Écrans blancs | le front compilé est dans l'image : reconstruire avec `.\scripts\demarrer.ps1` |
