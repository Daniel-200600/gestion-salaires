"""
Tests de utils/navigation.py — structure de navigation en 7 blocs
(correction finale). Logique pure, sans dépendance à Streamlit.

Adaptation (amélioration professionnelle) : les noms de blocs ne
portent plus d'emoji (interdits comme icônes d'interface) et quatre
pages de documentation (guide utilisateur, politique de
confidentialité, conditions d'utilisation, guide administrateur) ont
été ajoutées À L'INTÉRIEUR des blocs existants. Les assertions portant
sur les noms à emoji et sur le total de 17 entrées ont été ajustées en
conséquence ; les 17 pages fonctionnelles restent vérifiées une à une.
"""

from models.enums import RoleUtilisateur
from utils.navigation import (
    DEFINITION_BLOCS,
    PAGES_DOCUMENTATION,
    construire_blocs_visibles,
    entrees_fonctionnelles,
    toutes_les_entrees,
)


def test_exactement_sept_blocs_definis():
    assert len(DEFINITION_BLOCS) == 7


def test_dix_sept_pages_reparties_sans_perte():
    assert len(entrees_fonctionnelles()) == 17
    assert len(toutes_les_entrees()) == 17 + len(PAGES_DOCUMENTATION)


def test_noms_des_sept_blocs_conformes_au_cahier_des_charges():
    noms_attendus = {
        "Tableau de bord", "Gestion", "Paie", "Contrôle & Historique",
        "Analyse & Rapports", "Documents & Opérations", "Administration & Sécurité",
    }
    noms_reels = set(DEFINITION_BLOCS.keys())
    assert noms_reels == noms_attendus


def test_aucun_doublon_de_chemin_entre_les_blocs():
    chemins = [e.chemin for e in toutes_les_entrees()]
    assert len(chemins) == len(set(chemins))


def test_toutes_les_pages_pointent_vers_ui_pages_jamais_vers_pages():
    for entree in toutes_les_entrees():
        assert entree.chemin.startswith("ui_pages/")
        assert not entree.chemin.startswith("pages/")


def test_un_seul_chemin_par_defaut_le_tableau_de_bord():
    entrees_par_defaut = [e for e in toutes_les_entrees() if e.defaut]
    assert len(entrees_par_defaut) == 1
    assert entrees_par_defaut[0].titre == "Tableau de bord"


def test_composition_exacte_de_chaque_bloc():
    attendu = {
        "Tableau de bord": [
            "Tableau de bord", "Guide utilisateur", "Politique de confidentialité", "Conditions d'utilisation",
        ],
        "Gestion": ["Enseignants", "Périodes de paie"],
        "Paie": ["Données de paie", "Calcul de paie", "Cycle de paie", "Bulletins de solde", "Génération comptable"],
        "Contrôle & Historique": ["Contrôle de la paie", "Historique de paie"],
        "Analyse & Rapports": ["Rapports comptables", "Statistiques"],
        "Documents & Opérations": ["Gestion des documents", "Importation", "Notifications", "Automatisation"],
        "Administration & Sécurité": ["Administration", "Guide administrateur"],
    }
    for nom_bloc, titres_attendus in attendu.items():
        titres_reels = [e.titre for e in DEFINITION_BLOCS[nom_bloc]]
        assert titres_reels == titres_attendus, f"Bloc {nom_bloc} : attendu {titres_attendus}, obtenu {titres_reels}"


def test_admin_voit_les_sept_blocs():
    blocs = construire_blocs_visibles(RoleUtilisateur.ADMIN)
    assert len(blocs) == 7


def test_admin_voit_les_dix_sept_pages():
    blocs = construire_blocs_visibles(RoleUtilisateur.ADMIN)
    visibles = [e for entrees in blocs.values() for e in entrees]
    assert len([e for e in visibles if e.chemin not in PAGES_DOCUMENTATION]) == 17
    assert len(visibles) == 17 + len(PAGES_DOCUMENTATION)


def test_consultation_ne_voit_pas_le_bloc_administration():
    blocs = construire_blocs_visibles(RoleUtilisateur.CONSULTATION)
    assert "Administration & Sécurité" not in blocs


def test_gestionnaire_paie_voit_moins_que_admin():
    blocs_admin = construire_blocs_visibles(RoleUtilisateur.ADMIN)
    blocs_gestionnaire = construire_blocs_visibles(RoleUtilisateur.GESTIONNAIRE_PAIE)
    total_admin = sum(len(e) for e in blocs_admin.values())
    total_gestionnaire = sum(len(e) for e in blocs_gestionnaire.values())
    assert total_gestionnaire <= total_admin


def test_aucun_bloc_vide_jamais_retourne():
    for role in RoleUtilisateur:
        blocs = construire_blocs_visibles(role)
        for nom_bloc, entrees in blocs.items():
            assert len(entrees) > 0, f"Bloc vide retourné pour {role} : {nom_bloc}"


def test_role_none_ne_voit_aucun_bloc():
    blocs = construire_blocs_visibles(None)
    assert blocs == {}


def test_tableau_de_bord_visible_pour_tous_les_roles_operationnels():
    for role in RoleUtilisateur:
        blocs = construire_blocs_visibles(role)
        assert "Tableau de bord" in blocs
