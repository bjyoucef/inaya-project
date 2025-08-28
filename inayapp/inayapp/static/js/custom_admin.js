// Attendre que le DOM soit complètement chargé
document.addEventListener("DOMContentLoaded", function () {
  // Alerte de bienvenue (exemple simple)
  if (document.querySelector(".jazzmin-ui")) {
    alert("Bienvenue dans l'interface admin modernisée avec Jazzmin !");
  }

  // Changer la couleur de fond du header
  const header = document.querySelector(".jazzmin-header");
  if (header) {
    header.style.backgroundColor = "#2c3e50"; // Couleur sombre élégante
  }

  // Ajouter un effet au clic sur les boutons de soumission
  const submitButtons = document.querySelectorAll(
    '.jazzmin-form input[type="submit"]'
  );
  submitButtons.forEach((button) => {
    button.addEventListener("click", function () {
      button.style.backgroundColor = "#27ae60"; // Vert au clic
      button.style.transition = "background-color 0.3s ease";
      setTimeout(() => {
        button.style.backgroundColor = ""; // Revenir à la couleur par défaut
      }, 300);
    });
  });

  // Exemple : Ajouter une classe personnalisée à la barre latérale
  const sidebar = document.querySelector(".jazzmin-sidebar");
  if (sidebar) {
    sidebar.classList.add("custom-sidebar");
  }

  // Exemple : Afficher/masquer un élément spécifique (ex. un champ)
  const toggleFields = document.querySelectorAll(".fieldBox");
  toggleFields.forEach((field) => {
    field.addEventListener("click", function () {
      field.style.backgroundColor = "#f1f1f1"; // Fond clair au clic
    });
  });
});

// Fonction utilitaire pour logger dans la console (pour débogage)
function logAdminAction(message) {
  console.log(`[Admin Custom JS] ${message}`);
}

logAdminAction("Fichier custom_admin.js chargé avec succès.");
