# 05 — Note sur les données personnelles

## Principes appliqués
- **Pseudonymisation** : l'identifiant client et le nom du technicien sont remplacés par une
  empreinte salée (`PX_…`). En production : HMAC-SHA256 avec secret hors dépôt.
- **Minimisation** : la position GPS du client (recherches) est supprimée — seule la station est
  conservée. Les données identifiantes du référentiel clients (nom, e-mail, téléphone, naissance)
  ne sont pas chargées.
- **Frontière** : aucune donnée identifiante n'atteint les couches Silver et Gold, seules exposées
  à l'interface. Les analyses portent sur le service, jamais sur une personne identifiable.

## Vérification (sur les données)
- Colonnes de `silver_trajets` : trajet_id, client_px, engin_id, type_engin, ville, station_depart, station_arrivee, debut, fin, duree_min, distance_km, montant_eur, moyen_paiement, _source_file, _rn, flag_client_inconnu, flag_duree_incoherente, jour, heure
- Colonnes de `silver_recherches` : recherche_id, ts, client_px, ville, station_id, nb_engins_affiches, resultat, trajet_id, _rn, flag_nb_engins_absent, jour, heure

Aucune colonne `client_id`, `lat` ni `lon` côté client : seuls subsistent `client_px` et `station_id`.
