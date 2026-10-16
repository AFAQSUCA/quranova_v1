# Chapitre 33 — Sécurité des comptes du personnel (phase 4, A1 à A3 ; §15.1)

## Objectif
Fermer les trois écarts du CdC §15.1 avant tout compte réel : mots de passe de 12 caractères, limitation des tentatives de connexion, deuxième facteur obligatoire.

## A1 — Mots de passe de 12 caractères
`MinimumLengthValidator` à 12 dans `config/settings/base.py`. Le hachage reste PBKDF2 (liste par défaut de Django) ; le CdC accepte PBKDF2 ou Argon2.
Tests : `apps/utilisateurs/tests/test_mots_de_passe.py` (y compris le formulaire de création de compte de l'administration).

## A2 — Limitation des tentatives de connexion
- 5 échecs d'un même compte en 15 min : compte verrouillé, **même avec le bon mot de passe** ; 20 échecs d'une même adresse : adresse verrouillée ;
  une connexion réussie remet à zéro le compteur du compte ; le verrou expire seul ; il est journalisé **une fois** (`connexion.verrouillee`).
- Où : `apps/utilisateurs/connexion.py` (règles), `backends.py` (le verrou est **dans le backend d'authentification**, donc valable pour toute voie de connexion),
  `formulaires.py` (message clair à l'écran), modèle `TentativeConnexion`.
- **Désactivation immédiate** : décocher « actif » coupe aussi la session en cours (testé).
- **Trouvaille importante** : derrière Nginx, `REMOTE_ADDR` est l'adresse de Nginx pour tous. La limitation « par adresse » (et celle des codes de juré, qui existait déjà !)
  aurait bloqué **toutes les tablettes en même temps** après 5 mauvais codes. `apps/commun/reseau.py` lit `X-Real-IP` (posé par Nginx) quand `PROXY_DE_CONFIANCE` est vrai (production).
  Test : deux tablettes derrière Nginx ne partagent pas leurs 5 essais.

## A3 — Deuxième facteur TOTP
- TOTP = code à 6 chiffres renouvelé toutes les 30 s par une application d'authentification (FreeOTP, Google Authenticator…) : **fonctionne sans Internet**.
- Dépendances validées : `django-otp` (anti-rejeu, ralentissement des essais) et `qrcode` (QR en SVG, sans Pillow).
- **Qui** : administrateur et opérateurs. Pas le responsable client (le CdC ne l'exige pas). **Où** : toutes les pages à session (administration, commande, documents),
  les API de session (403 JSON `2fa_requise`) **et le WebSocket de commande** (règle absolue n° 4).
- **Premier passage** : page `/compte/2fa/` avec QR code et clé de saisie manuelle ; l'appareil n'est actif qu'après un bon code. Ensuite : saisie du code à chaque connexion.
- **Téléphone perdu** : un administrateur utilise l'action « Réinitialiser le deuxième facteur » (journalisée) ; la personne se ré-enrôle à sa prochaine connexion.
- **Développement** : `EXIGER_2FA = False` dans `dev.py` pour que les comptes de démonstration marchent avec leur seul mot de passe ; la production garde `True` (testé).

## Commandes (PowerShell)
```powershell
pip install -r requirements\dev.txt
python manage.py migrate
pytest apps\utilisateurs apps\presentation\tests\test_consumer.py apps\commun\tests\test_reglages_production.py
# Essayer le 2FA en local : dans .env ou dans un dev_2fa.py, mettre EXIGER_2FA = True (voir config\settings\dev.py)
```

## Résultat attendu
Tous les tests passent ; avec `EXIGER_2FA = True`, la connexion à `/admin/` mène à la page d'activation, puis exige le code à chaque session.

**Question :** pourquoi le verrou de connexion est-il placé dans le backend d'authentification et pas seulement dans le formulaire de la page de connexion ?
