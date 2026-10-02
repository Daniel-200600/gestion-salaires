"""
Tests de services/backup_service.py (module 10).

Toutes les bases et tous les dossiers de sauvegarde utilisés ici sont
temporaires (tmp_path) — aucun test ne touche jamais à une base réelle
de développement.
"""

import sqlite3
import time

import pytest

from database.initialization import init_database
from services import backup_service, enseignant_service
from services.backup_service import BackupServiceError


@pytest.fixture
def base_avec_donnees(tmp_path):
    """Une base SQLite temporaire, initialisée et contenant un enseignant."""
    db_path = tmp_path / "app.db"
    init_database(db_path=db_path)
    enseignant_service.creer_enseignant(
        nom="Fouda", prenom="Alain", sexe="M", statut="P", taux_horaire=1000, db_path=db_path
    )
    return db_path


@pytest.fixture
def dossier_sauvegardes(tmp_path):
    return tmp_path / "backups"


# ---------------------------------------------------------------------
# Création d'une sauvegarde
# ---------------------------------------------------------------------

def test_creation_sauvegarde(base_avec_donnees, dossier_sauvegardes):
    chemin = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    assert chemin.exists()
    assert chemin.stat().st_size > 0


def test_nom_sauvegarde_correct(base_avec_donnees, dossier_sauvegardes):
    chemin = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    assert chemin.name.startswith("backup_")
    assert chemin.suffix == ".db"


def test_dossier_sauvegarde_cree_automatiquement(base_avec_donnees, tmp_path):
    dossier_inexistant = tmp_path / "nouveau_dossier" / "backups"
    assert not dossier_inexistant.exists()
    backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_inexistant)
    assert dossier_inexistant.exists()


def test_sauvegarde_contient_les_donnees_reelles(base_avec_donnees, dossier_sauvegardes):
    chemin = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    conn = sqlite3.connect(chemin)
    conn.row_factory = sqlite3.Row
    ligne = conn.execute("SELECT nom FROM enseignants WHERE nom = 'Fouda'").fetchone()
    conn.close()
    assert ligne is not None


def test_sauvegarde_sans_collision_de_nom(base_avec_donnees, dossier_sauvegardes):
    chemin1 = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    chemin2 = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    assert chemin1 != chemin2
    assert chemin1.exists() and chemin2.exists()


def test_sauvegarde_base_source_absente(tmp_path, dossier_sauvegardes):
    with pytest.raises(BackupServiceError, match="introuvable"):
        backup_service.creer_sauvegarde(db_path=tmp_path / "absente.db", backup_dir=dossier_sauvegardes)


# ---------------------------------------------------------------------
# Vérification d'intégrité
# ---------------------------------------------------------------------

def test_integrite_sauvegarde_valide(base_avec_donnees, dossier_sauvegardes):
    chemin = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    resultat = backup_service.verifier_integrite(chemin)
    assert resultat.valide is True


def test_integrite_fichier_absent(tmp_path):
    resultat = backup_service.verifier_integrite(tmp_path / "inexistant.db")
    assert resultat.valide is False
    assert "n'existe pas" in resultat.message


def test_integrite_fichier_vide(tmp_path):
    fichier_vide = tmp_path / "vide.db"
    fichier_vide.touch()
    resultat = backup_service.verifier_integrite(fichier_vide)
    assert resultat.valide is False
    assert "vide" in resultat.message


def test_integrite_fichier_corrompu(tmp_path):
    fichier_corrompu = tmp_path / "corrompu.db"
    fichier_corrompu.write_bytes(b"CECI N'EST PAS UNE BASE SQLITE VALIDE")
    resultat = backup_service.verifier_integrite(fichier_corrompu)
    assert resultat.valide is False


# ---------------------------------------------------------------------
# Historique des sauvegardes
# ---------------------------------------------------------------------

def test_liste_sauvegardes_vide_si_dossier_absent(tmp_path):
    sauvegardes = backup_service.lister_sauvegardes(backup_dir=tmp_path / "absent")
    assert sauvegardes == []


def test_liste_sauvegardes_metadonnees_correctes(base_avec_donnees, dossier_sauvegardes):
    chemin = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    sauvegardes = backup_service.lister_sauvegardes(backup_dir=dossier_sauvegardes)
    assert len(sauvegardes) == 1
    assert sauvegardes[0].nom == chemin.name
    assert sauvegardes[0].taille_octets > 0
    assert "o" in sauvegardes[0].taille_lisible or "Ko" in sauvegardes[0].taille_lisible


def test_liste_sauvegardes_triee_plus_recente_dabord(base_avec_donnees, dossier_sauvegardes):
    chemin1 = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    time.sleep(1.1)  # garantit un horodatage différent (granularité à la seconde)
    chemin2 = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    sauvegardes = backup_service.lister_sauvegardes(backup_dir=dossier_sauvegardes)
    assert sauvegardes[0].nom == chemin2.name


# ---------------------------------------------------------------------
# Restauration
# ---------------------------------------------------------------------

def test_restauration_reussie(base_avec_donnees, dossier_sauvegardes):
    chemin_sauvegarde = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)

    # Modifie la base après la sauvegarde.
    enseignant_service.creer_enseignant(
        nom="Nouveau", prenom="Apres", sexe="F", statut="V", taux_horaire=2000, db_path=base_avec_donnees
    )
    assert len(enseignant_service.lister_enseignants(inclure_inactifs=True, db_path=base_avec_donnees)) == 2

    rapport = backup_service.restaurer_sauvegarde(
        chemin_sauvegarde, confirmation=True, db_path=base_avec_donnees, backup_dir=dossier_sauvegardes
    )
    assert rapport.reussie is True

    enseignants_restaures = enseignant_service.lister_enseignants(inclure_inactifs=True, db_path=base_avec_donnees)
    assert len(enseignants_restaures) == 1
    assert enseignants_restaures[0].nom == "Fouda"


def test_restauration_cree_sauvegarde_de_securite(base_avec_donnees, dossier_sauvegardes):
    chemin_sauvegarde = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    rapport = backup_service.restaurer_sauvegarde(
        chemin_sauvegarde, confirmation=True, db_path=base_avec_donnees, backup_dir=dossier_sauvegardes
    )
    assert rapport.sauvegarde_securite is not None
    assert rapport.sauvegarde_securite.exists()
    assert rapport.sauvegarde_securite.name.startswith("avant_restauration_")


def test_restauration_sans_confirmation_refusee(base_avec_donnees, dossier_sauvegardes):
    chemin_sauvegarde = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    with pytest.raises(BackupServiceError, match="confirmation"):
        backup_service.restaurer_sauvegarde(
            chemin_sauvegarde, confirmation=False, db_path=base_avec_donnees, backup_dir=dossier_sauvegardes
        )


def test_restauration_fichier_invalide_refusee(base_avec_donnees, dossier_sauvegardes, tmp_path):
    fichier_corrompu = tmp_path / "corrompu.db"
    fichier_corrompu.write_bytes(b"PAS UNE BASE SQLITE")

    rapport = backup_service.restaurer_sauvegarde(
        fichier_corrompu, confirmation=True, db_path=base_avec_donnees, backup_dir=dossier_sauvegardes
    )
    assert rapport.reussie is False
    assert "invalide" in rapport.message.lower() or "sqlite" in rapport.message.lower()

    # La base active n'a pas été touchée.
    assert len(enseignant_service.lister_enseignants(inclure_inactifs=True, db_path=base_avec_donnees)) == 1


def test_restauration_fichier_absent_refusee(base_avec_donnees, dossier_sauvegardes, tmp_path):
    rapport = backup_service.restaurer_sauvegarde(
        tmp_path / "absent.db", confirmation=True, db_path=base_avec_donnees, backup_dir=dossier_sauvegardes
    )
    assert rapport.reussie is False


def test_restauration_journalisee_dans_audit(base_avec_donnees, dossier_sauvegardes):
    from database.connection import get_connection

    chemin_sauvegarde = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    backup_service.restaurer_sauvegarde(
        chemin_sauvegarde, confirmation=True, db_path=base_avec_donnees, backup_dir=dossier_sauvegardes
    )
    with get_connection(base_avec_donnees) as conn:
        lignes = conn.execute(
            "SELECT * FROM audit_log WHERE type_action = 'restauration_sauvegarde'"
        ).fetchall()
    assert len(lignes) == 1
    assert "Succès" in lignes[0]["details"]


def test_restauration_echec_journalise_aussi(base_avec_donnees, dossier_sauvegardes, tmp_path):
    from database.connection import get_connection

    fichier_corrompu = tmp_path / "corrompu.db"
    fichier_corrompu.write_bytes(b"INVALIDE")
    backup_service.restaurer_sauvegarde(
        fichier_corrompu, confirmation=True, db_path=base_avec_donnees, backup_dir=dossier_sauvegardes
    )
    with get_connection(base_avec_donnees) as conn:
        lignes = conn.execute(
            "SELECT * FROM audit_log WHERE type_action = 'restauration_sauvegarde'"
        ).fetchall()
    assert len(lignes) == 1
    assert "Refusé" in lignes[0]["details"]


# ---------------------------------------------------------------------
# Sauvegarde/restauration incluent les utilisateurs (module 11, section 45)
# ---------------------------------------------------------------------

def test_sauvegarde_inclut_les_utilisateurs(base_avec_donnees, dossier_sauvegardes):
    from models.enums import RoleUtilisateur
    from services import utilisateur_service

    utilisateur_service.creer_utilisateur(
        nom="Admin", prenom="Test", username="admintest", mot_de_passe="MotDePasse123",
        role=RoleUtilisateur.ADMIN, db_path=base_avec_donnees,
    )

    chemin_sauvegarde = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)

    conn = sqlite3.connect(chemin_sauvegarde)
    conn.row_factory = sqlite3.Row
    ligne = conn.execute("SELECT username, role FROM utilisateurs WHERE username = 'admintest'").fetchone()
    conn.close()
    assert ligne is not None
    assert ligne["role"] == "admin"


def test_restauration_conserve_les_utilisateurs(base_avec_donnees, dossier_sauvegardes):
    from models.enums import RoleUtilisateur
    from services import utilisateur_service

    utilisateur_service.creer_utilisateur(
        nom="Admin", prenom="Test", username="admintest", mot_de_passe="MotDePasse123",
        role=RoleUtilisateur.ADMIN, db_path=base_avec_donnees,
    )
    chemin_sauvegarde = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)

    # Ajoute un second utilisateur APRÈS la sauvegarde.
    utilisateur_service.creer_utilisateur(
        nom="Autre", prenom="User", username="autre", mot_de_passe="MotDePasse456",
        role=RoleUtilisateur.CONSULTATION, db_path=base_avec_donnees,
    )

    rapport = backup_service.restaurer_sauvegarde(
        chemin_sauvegarde, confirmation=True, db_path=base_avec_donnees, backup_dir=dossier_sauvegardes
    )
    assert rapport.reussie is True

    utilisateurs_restaures = utilisateur_service.lister_utilisateurs(db_path=base_avec_donnees)
    usernames = {u.username for u in utilisateurs_restaures}
    assert usernames == {"admintest"}  # retour à l'état sauvegardé (avant l'ajout du second utilisateur)


# ---------------------------------------------------------------------
# Préservation des statuts de période (module 12, section 26)
# ---------------------------------------------------------------------

def test_restauration_conserve_le_statut_cloture_dune_periode(base_avec_donnees, dossier_sauvegardes):
    """Une restauration ne doit jamais 'rouvrir' automatiquement une période clôturée."""
    from models.enums import StatutPeriode
    from services import controle_paie_service, donnees_paie_service, periode_service
    from services.donnees_paie_service import DonneesPaieEnseignant

    e = enseignant_service.creer_enseignant(
        nom="Test", prenom="Cycle", sexe="M", statut="P", taux_horaire=1000, db_path=base_avec_donnees
    )
    p = periode_service.creer_periode(mois=1, annee=2043, db_path=base_avec_donnees)
    controle_paie_service.ouvrir_periode_avec_audit(p.id, db_path=base_avec_donnees)
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        p.id, [DonneesPaieEnseignant(enseignant_id=e.id, heures_par_semaine={1: 10})], db_path=base_avec_donnees
    )
    controle_paie_service.valider_periode_avec_controle(p.id, confirmation=True, db_path=base_avec_donnees)
    controle_paie_service.cloturer_periode_avec_controle(p.id, confirmation=True, db_path=base_avec_donnees)

    chemin_sauvegarde = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)

    rapport = backup_service.restaurer_sauvegarde(
        chemin_sauvegarde, confirmation=True, db_path=base_avec_donnees, backup_dir=dossier_sauvegardes
    )
    assert rapport.reussie is True

    periode_restauree = periode_service.obtenir_periode(p.id, db_path=base_avec_donnees)
    assert periode_restauree.statut == StatutPeriode.CLOTUREE


def test_restauration_conserve_audit_du_cycle(base_avec_donnees, dossier_sauvegardes):
    from services import controle_paie_service, periode_service

    p = periode_service.creer_periode(mois=2, annee=2043, db_path=base_avec_donnees)
    controle_paie_service.ouvrir_periode_avec_audit(p.id, db_path=base_avec_donnees, utilisateur="testeur")

    chemin_sauvegarde = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    backup_service.restaurer_sauvegarde(
        chemin_sauvegarde, confirmation=True, db_path=base_avec_donnees, backup_dir=dossier_sauvegardes
    )

    from database.repositories import audit_log_repository
    entrees = audit_log_repository.lister_par_entite("periode_paie", p.id, db_path=base_avec_donnees)
    assert any(e.type_action.value == "periode_ouverte" and e.utilisateur == "testeur" for e in entrees)


# ---------------------------------------------------------------------
# Sauvegarde complète (base + documents) — module 14, section 36
# ---------------------------------------------------------------------

def test_sauvegarde_complete_inclut_base_et_documents(base_avec_donnees, dossier_sauvegardes, tmp_path):
    import zipfile

    dossier_documents = tmp_path / "documents"
    dossier_documents.mkdir()
    (dossier_documents / "bulletin_test.docx").write_bytes(b"contenu bulletin")

    chemin_zip = backup_service.creer_sauvegarde_complete(
        db_path=base_avec_donnees, dossier_documents=dossier_documents, backup_dir=dossier_sauvegardes
    )
    assert chemin_zip.exists()
    assert chemin_zip.name.startswith("Backup_Complet_")

    with zipfile.ZipFile(chemin_zip) as archive:
        noms = archive.namelist()
        assert any(n.startswith("base_de_donnees/") for n in noms)
        assert any("bulletin_test.docx" in n for n in noms)


def test_sauvegarde_complete_fonctionne_sans_documents(base_avec_donnees, dossier_sauvegardes):
    """Si aucun dossier de documents n'est fourni, la sauvegarde de la base seule reste incluse."""
    import zipfile

    chemin_zip = backup_service.creer_sauvegarde_complete(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    assert chemin_zip.exists()
    with zipfile.ZipFile(chemin_zip) as archive:
        assert any(n.startswith("base_de_donnees/") for n in archive.namelist())


def test_creer_sauvegarde_simple_reste_db_uniquement(base_avec_donnees, dossier_sauvegardes):
    """La fonction historique creer_sauvegarde() n'inclut jamais les documents — comportement inchangé."""
    chemin = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    assert chemin.suffix == ".db"  # toujours un simple fichier .db, jamais un ZIP


# ---------------------------------------------------------------------
# Modèles de bulletin importés (fichiers de data/modeles_bulletin/)
# ---------------------------------------------------------------------

def _creer_modele_importe(db_path, nom="modele_abc.docx", contenu=b"PK modele"):
    dossier = backup_service.dossier_modeles_de_la_base(db_path)
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / nom).write_bytes(contenu)
    return dossier / nom


def test_sauvegarde_emporte_les_modeles_importes(base_avec_donnees, dossier_sauvegardes):
    _creer_modele_importe(base_avec_donnees)
    sauvegarde = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    compagnon = backup_service.dossier_modeles_de_la_sauvegarde(sauvegarde)
    assert (compagnon / "modele_abc.docx").read_bytes() == b"PK modele"


def test_sauvegarde_sans_modele_ne_cree_pas_de_dossier_compagnon(base_avec_donnees, dossier_sauvegardes):
    sauvegarde = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    assert not backup_service.dossier_modeles_de_la_sauvegarde(sauvegarde).exists()


def test_dossier_compagnon_absent_de_la_liste_des_sauvegardes(base_avec_donnees, dossier_sauvegardes):
    _creer_modele_importe(base_avec_donnees)
    backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    assert [s.nom.endswith(".db") for s in backup_service.lister_sauvegardes(dossier_sauvegardes)] == [True]


def test_restauration_remet_en_place_les_modeles_perdus(base_avec_donnees, dossier_sauvegardes):
    modele = _creer_modele_importe(base_avec_donnees)
    sauvegarde = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    modele.unlink()  # ex. changement de PC : la base revient, pas le dossier des modèles

    rapport = backup_service.restaurer_sauvegarde(
        sauvegarde, confirmation=True, db_path=base_avec_donnees, backup_dir=dossier_sauvegardes
    )

    assert rapport.reussie
    assert modele.read_bytes() == b"PK modele"
    assert "1 modèle(s) de bulletin remis en place" in rapport.message


def test_restauration_n_ecrase_jamais_un_modele_present(base_avec_donnees, dossier_sauvegardes):
    modele = _creer_modele_importe(base_avec_donnees, contenu=b"PK version sauvegardee")
    sauvegarde = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    modele.write_bytes(b"PK version actuelle")

    rapport = backup_service.restaurer_sauvegarde(
        sauvegarde, confirmation=True, db_path=base_avec_donnees, backup_dir=dossier_sauvegardes
    )

    assert rapport.reussie
    assert modele.read_bytes() == b"PK version actuelle"


def test_sauvegarde_complete_contient_les_modeles(base_avec_donnees, dossier_sauvegardes):
    import zipfile

    _creer_modele_importe(base_avec_donnees, nom="modele_abc.pdf", contenu=b"%PDF modele")
    chemin_zip = backup_service.creer_sauvegarde_complete(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    with zipfile.ZipFile(chemin_zip) as archive:
        assert archive.read("modeles_bulletin/modele_abc.pdf") == b"%PDF modele"


# ---------------------------------------------------------------------
# Sauvegarde automatique quotidienne
# ---------------------------------------------------------------------

def _vieillir(chemin, jours):
    """Recule la date d'une sauvegarde (la date affichée est celle du fichier)."""
    import os

    horodatage = time.time() - jours * 86400
    os.utime(chemin, (horodatage, horodatage))


def test_sauvegarde_automatique_creee_au_premier_usage(base_avec_donnees, dossier_sauvegardes):
    chemin = backup_service.sauvegarde_automatique_si_necessaire(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    assert chemin is not None and chemin.name.startswith(backup_service.PREFIXE_SAUVEGARDE_AUTO)
    assert backup_service.verifier_integrite(chemin).valide


def test_une_seule_sauvegarde_automatique_par_jour(base_avec_donnees, dossier_sauvegardes):
    assert backup_service.sauvegarde_automatique_si_necessaire(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    assert backup_service.sauvegarde_automatique_si_necessaire(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes) is None
    assert len(backup_service.lister_sauvegardes_automatiques(dossier_sauvegardes)) == 1


def test_nouvelle_sauvegarde_automatique_le_lendemain(base_avec_donnees, dossier_sauvegardes):
    hier = backup_service.sauvegarde_automatique_si_necessaire(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    _vieillir(hier, 1)
    time.sleep(1.1)  # noms horodatés à la seconde
    assert backup_service.sauvegarde_automatique_si_necessaire(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    assert len(backup_service.lister_sauvegardes_automatiques(dossier_sauvegardes)) == 2


def test_seules_les_sauvegardes_automatiques_recentes_sont_conservees(base_avec_donnees, dossier_sauvegardes):
    manuelle = backup_service.creer_sauvegarde(db_path=base_avec_donnees, backup_dir=dossier_sauvegardes)
    _vieillir(manuelle, 30)
    anciennes = []
    for jours in (5, 4, 3):
        chemin = backup_service.creer_sauvegarde(
            db_path=base_avec_donnees, backup_dir=dossier_sauvegardes, prefixe=backup_service.PREFIXE_SAUVEGARDE_AUTO
        )
        compagnon = backup_service.dossier_modeles_de_la_sauvegarde(chemin)
        compagnon.mkdir()
        _vieillir(chemin, jours)
        anciennes.append((chemin, compagnon))

    backup_service.sauvegarde_automatique_si_necessaire(
        db_path=base_avec_donnees, backup_dir=dossier_sauvegardes, conserver=2
    )

    noms = [s.nom for s in backup_service.lister_sauvegardes_automatiques(dossier_sauvegardes)]
    assert len(noms) == 2 and anciennes[2][0].name in noms  # la nouvelle + la plus récente des anciennes
    for chemin, compagnon in anciennes[:2]:
        assert not chemin.exists() and not compagnon.exists()
    assert manuelle.exists()  # une sauvegarde manuelle n'est jamais supprimée


def test_sauvegarde_automatique_ne_leve_jamais(tmp_path, dossier_sauvegardes):
    assert backup_service.sauvegarde_automatique_si_necessaire(
        db_path=tmp_path / "absente.db", backup_dir=dossier_sauvegardes
    ) is None
