// static/admin/js/custom_admin.js

document.addEventListener("DOMContentLoaded", function () {
  // Amélioration des calculs automatiques dans les inlines
  function setupAutoCalculations() {
    // Calcul automatique des prix totaux dans LocationBlocActe
    const acteInlines = document.querySelectorAll(
      "#locationblocacte_set-group .form-row"
    );
    acteInlines.forEach(function (row) {
      const quantiteField = row.querySelector('input[id$="-quantite"]');
      const prixUnitaireField = row.querySelector(
        'input[id$="-prix_unitaire"]'
      );
      const prixTotalField = row.querySelector('input[id$="-prix_total"]');

      if (quantiteField && prixUnitaireField && prixTotalField) {
        function calculateTotal() {
          const quantite = parseFloat(quantiteField.value) || 0;
          const prixUnitaire = parseFloat(prixUnitaireField.value) || 0;
          const total = quantite * prixUnitaire;
          prixTotalField.value = total.toFixed(2);
        }

        quantiteField.addEventListener("input", calculateTotal);
        prixUnitaireField.addEventListener("input", calculateTotal);
      }
    });

    // Calcul automatique des écarts dans ConsommationProduitBloc
    const produitInlines = document.querySelectorAll(
      "#consommationproduitbloc_set-group .form-row"
    );
    produitInlines.forEach(function (row) {
      const quantiteField = row.querySelector('input[id$="-quantite"]');
      const quantiteIncluseField = row.querySelector(
        'input[id$="-quantite_incluse"]'
      );
      const ecartField = row.querySelector('input[id$="-ecart_quantite"]');
      const estInclusField = row.querySelector('input[id$="-est_inclus"]');

      if (quantiteField && quantiteIncluseField && ecartField) {
        function calculateEcart() {
          const quantite = parseFloat(quantiteField.value) || 0;
          const quantiteIncluse = parseFloat(quantiteIncluseField.value) || 0;
          const ecart = quantite - quantiteIncluse;

          ecartField.value = ecart.toFixed(2);

          if (estInclusField) {
            estInclusField.checked = ecart <= 0;
          }

          // Colorer le champ selon l'écart
          if (ecart > 0) {
            ecartField.style.backgroundColor = "#fff3cd";
            ecartField.style.color = "#856404";
          } else if (ecart < 0) {
            ecartField.style.backgroundColor = "#d4edda";
            ecartField.style.color = "#155724";
          } else {
            ecartField.style.backgroundColor = "#e2e3e5";
            ecartField.style.color = "#6c757d";
          }
        }

        quantiteField.addEventListener("input", calculateEcart);
        quantiteIncluseField.addEventListener("input", calculateEcart);

        // Calcul initial
        calculateEcart();
      }
    });
  }

  // Configuration des tooltips pour les champs d'aide
  function setupTooltips() {
    const helpTexts = document.querySelectorAll(".help_text");
    helpTexts.forEach(function (helpText) {
      helpText.style.cursor = "help";
      helpText.title = helpText.textContent;
    });
  }

  // Amélioration des sélecteurs de forfait
  function setupForfaitHandling() {
    const typeTarificationField = document.querySelector(
      "#id_type_tarification"
    );
    const forfaitField = document.querySelector("#id_forfait");
    const forfaitRow = forfaitField ? forfaitField.closest(".form-row") : null;

    if (typeTarificationField && forfaitField && forfaitRow) {
      function toggleForfaitField() {
        if (typeTarificationField.value === "FORFAIT") {
          forfaitRow.style.display = "block";
          forfaitField.required = true;
        } else {
          forfaitRow.style.display = "none";
          forfaitField.required = false;
          forfaitField.value = "";
        }
      }

      typeTarificationField.addEventListener("change", toggleForfaitField);
      toggleForfaitField(); // Appel initial
    }
  }

  // Amélioration de l'affichage des statuts
  function enhanceStatusDisplay() {
    // Ajouter des classes CSS aux cellules de statut
    const statutCells = document.querySelectorAll("td");
    statutCells.forEach(function (cell) {
      const text = cell.textContent.trim();

      // Statuts de paiement
      if (text === "Équilibré") {
        cell.innerHTML =
          '<span class="status-badge status-equilibre">Équilibré</span>';
      } else if (text === "Surplus à verser au médecin") {
        cell.innerHTML =
          '<span class="status-badge status-surplus">Surplus</span>';
      } else if (text === "Complément dû par le médecin") {
        cell.innerHTML =
          '<span class="status-badge status-complement">Complément</span>';
      } else if (text === "Aucun paiement enregistré") {
        cell.innerHTML = '<span class="status-badge status-aucun">Aucun</span>';
      }

      // Statuts actif/inactif
      if (text === "True" && cell.querySelector('img[alt="True"]')) {
        cell.innerHTML =
          '<span class="status-badge status-active">Actif</span>';
      } else if (text === "False" && cell.querySelector('img[alt="False"]')) {
        cell.innerHTML =
          '<span class="status-badge status-inactive">Inactif</span>';
      }
    });
  }

  // Configuration des filtres rapides
  function setupQuickFilters() {
    // Ajouter des boutons de filtre rapide
    const changelistSearch = document.querySelector("#changelist-search");
    if (changelistSearch) {
      const quickFilters = document.createElement("div");
      quickFilters.className = "quick-filters";
      quickFilters.style.marginBottom = "10px";

      // Boutons pour les statuts courants
      if (window.location.pathname.includes("locationbloc")) {
        const filters = [
          { label: "Aujourd'hui", param: "date_operation__date=today" },
          { label: "Cette semaine", param: "date_operation__week=current" },
          { label: "Non réglés", param: "is_reglement_complet=False" },
          { label: "Forfaitaire", param: "type_tarification=FORFAIT" },
        ];

        filters.forEach(function (filter) {
          const button = document.createElement("button");
          button.textContent = filter.label;
          button.className = "button";
          button.style.marginRight = "5px";
          button.style.fontSize = "12px";
          button.style.padding = "4px 8px";

          button.addEventListener("click", function (e) {
            e.preventDefault();
            const currentUrl = new URL(window.location);
            const params = new URLSearchParams(currentUrl.search);

            // Ajouter ou remplacer le paramètre de filtre
            const [key, value] = filter.param.split("=");
            params.set(key, value);

            window.location.search = params.toString();
          });

          quickFilters.appendChild(button);
        });

        changelistSearch.parentNode.insertBefore(
          quickFilters,
          changelistSearch
        );
      }
    }
  }

  // Configuration du tri des colonnes
  function enhanceColumnSorting() {
    const headers = document.querySelectorAll(".results th.sortable");
    headers.forEach(function (header) {
      header.style.cursor = "pointer";
      header.addEventListener("mouseenter", function () {
        this.style.backgroundColor = "#2c5aa0";
      });
      header.addEventListener("mouseleave", function () {
        this.style.backgroundColor = "#417690";
      });
    });
  }

  // Configuration des confirmations de suppression
  function setupDeleteConfirmations() {
    const deleteButtons = document.querySelectorAll(
      'input[value="Delete selected items"], .deletelink'
    );
    deleteButtons.forEach(function (button) {
      button.addEventListener("click", function (e) {
        if (!confirm("Êtes-vous sûr de vouloir supprimer ces éléments ?")) {
          e.preventDefault();
        }
      });
    });
  }

  // Amélioration de la navigation dans les inlines
  function enhanceInlineNavigation() {
    const inlineGroups = document.querySelectorAll(".inline-group");
    inlineGroups.forEach(function (group) {
      const addButton = group.querySelector(".add-row a");
      if (addButton) {
        addButton.style.background = "#28a745";
        addButton.style.color = "white";
        addButton.style.padding = "5px 10px";
        addButton.style.borderRadius = "3px";
        addButton.style.textDecoration = "none";
        addButton.style.fontSize = "12px";

        addButton.addEventListener("mouseenter", function () {
          this.style.background = "#218838";
        });
        addButton.addEventListener("mouseleave", function () {
          this.style.background = "#28a745";
        });
      }
    });
  }

  // Configuration des raccourcis clavier
  function setupKeyboardShortcuts() {
    document.addEventListener("keydown", function (e) {
      // Ctrl+S pour sauvegarder
      if (e.ctrlKey && e.key === "s") {
        e.preventDefault();
        const saveButton = document.querySelector('input[name="_save"]');
        if (saveButton) {
          saveButton.click();
        }
      }

      // Ctrl+N pour nouveau
      if (e.ctrlKey && e.key === "n") {
        e.preventDefault();
        const addButton = document.querySelector(".addlink");
        if (addButton) {
          window.location.href = addButton.href;
        }
      }

      // Escape pour retour à la liste
      if (e.key === "Escape") {
        const breadcrumbs = document.querySelector(".breadcrumbs a");
        if (breadcrumbs) {
          window.location.href = breadcrumbs.href;
        }
      }
    });
  }

  // Configuration des validations côté client
  function setupClientValidations() {
    // Validation des montants positifs
    const priceFields = document.querySelectorAll(
      'input[id*="prix"], input[id*="montant"]'
    );
    priceFields.forEach(function (field) {
      field.addEventListener("input", function () {
        const value = parseFloat(this.value);
        if (value < 0) {
          this.style.borderColor = "#dc3545";
          this.title = "La valeur ne peut pas être négative";
        } else {
          this.style.borderColor = "#ced4da";
          this.title = "";
        }
      });
    });

    // Validation des durées
    const dureeFields = document.querySelectorAll('input[id*="duree"]');
    dureeFields.forEach(function (field) {
      field.addEventListener("input", function () {
        const value = parseInt(this.value);
        if (value <= 0) {
          this.style.borderColor = "#dc3545";
          this.title = "La durée doit être positive";
        } else {
          this.style.borderColor = "#ced4da";
          this.title = "";
        }
      });
    });
  }

  // Configuration de l'auto-sauvegarde (brouillon)
  function setupAutoSave() {
    let autoSaveTimeout;
    const form =
      document.querySelector("#changelist-search").closest("form") ||
      document.querySelector("form");

    if (form) {
      const inputs = form.querySelectorAll("input, select, textarea");
      inputs.forEach(function (input) {
        input.addEventListener("input", function () {
          clearTimeout(autoSaveTimeout);
          autoSaveTimeout = setTimeout(function () {
            // Sauvegarder les données dans le localStorage
            const formData = new FormData(form);
            const data = {};
            for (let [key, value] of formData.entries()) {
              data[key] = value;
            }
            localStorage.setItem(
              "admin_form_draft_" + window.location.pathname,
              JSON.stringify(data)
            );

            // Afficher un indicateur de sauvegarde
            showSaveIndicator();
          }, 2000);
        });
      });
    }
  }

  function showSaveIndicator() {
    const indicator = document.createElement("div");
    indicator.textContent = "Brouillon sauvegardé";
    indicator.style.position = "fixed";
    indicator.style.top = "10px";
    indicator.style.right = "10px";
    indicator.style.background = "#28a745";
    indicator.style.color = "white";
    indicator.style.padding = "5px 10px";
    indicator.style.borderRadius = "3px";
    indicator.style.fontSize = "12px";
    indicator.style.zIndex = "9999";

    document.body.appendChild(indicator);

    setTimeout(function () {
      indicator.remove();
    }, 2000);
  }

  // Initialisation de tous les modules
  setupAutoCalculations();
  setupTooltips();
  setupForfaitHandling();
  enhanceStatusDisplay();
  setupQuickFilters();
  enhanceColumnSorting();
  setupDeleteConfirmations();
  enhanceInlineNavigation();
  setupKeyboardShortcuts();
  setupClientValidations();
  setupAutoSave();

  // Réinitialiser les fonctions lors de l'ajout de nouvelles lignes inline
  document.addEventListener("click", function (e) {
    if (e.target.classList.contains("add-row")) {
      setTimeout(function () {
        setupAutoCalculations();
        setupClientValidations();
      }, 100);
    }
  });

  console.log("Admin personnalisé initialisé avec succès");
});
