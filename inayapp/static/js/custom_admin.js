// Attendre que le DOM soit complètement chargé
document.addEventListener("DOMContentLoaded", function () {
  // Alerte de bienvenue (optionnelle)
  if (document.querySelector(".jazzmin-ui")) {
    alert("Bienvenue dans l'admin avec Jazzmin et CKEditor 5 !");
  }

  // Changer la couleur de fond du header Jazzmin
  const header = document.querySelector(".jazzmin-header");
  if (header) {
    header.style.backgroundColor = "#2c3e50"; // Couleur sombre élégante
  }

  // Ajouter un bouton de prévisualisation pour CKEditor 5
  const ckeditorFields = document.querySelectorAll(
    ".django-ckeditor-5-container"
  );
  ckeditorFields.forEach((field, index) => {
    const previewButton = document.createElement("button");
    previewButton.innerText = "Prévisualiser le contenu";
    previewButton.className = "preview-btn";
    previewButton.style.marginTop = "10px";
    previewButton.style.padding = "8px 12px";
    previewButton.style.backgroundColor = "#3498db";
    previewButton.style.color = "white";
    previewButton.style.border = "none";
    previewButton.style.cursor = "pointer";

    previewButton.addEventListener("click", function () {
      const editorId = field.querySelector("div[data-ckeditor-5]").id;
      const editorInstance = window.CKEDITOR_5_instances[editorId];
      if (editorInstance) {
        const content = editorInstance.getData();
        const previewWindow = window.open(
          "",
          "PreviewWindow",
          "width=800,height=600"
        );
        previewWindow.document.write(`
                    <html>
                        <head><title>Prévisualisation</title></head>
                        <body style="padding: 20px;">${content}</body>
                    </html>
                `);
        previewWindow.document.close();
      } else {
        console.error("Éditeur CKEditor 5 non trouvé pour ID:", editorId);
      }
    });

    field.parentElement.appendChild(previewButton);
  });

  // Ajouter une classe personnalisée à la barre latérale
  const sidebar = document.querySelector(".jazzmin-sidebar");
  if (sidebar) {
    sidebar.classList.add("custom-sidebar");
  }

  // Effet au clic sur les boutons de soumission
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
});

// Fonction utilitaire pour logger dans la console
function logAdminAction(message) {
  console.log(`[Admin Custom JS] ${message}`);
}

logAdminAction("Fichier custom_admin.js chargé avec CKEditor 5.");
