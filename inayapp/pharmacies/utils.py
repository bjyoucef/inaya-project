# pharmacies/utils.py
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from django.core.files import File
from reportlab.platypus import SimpleDocTemplate, Table, Paragraph, Spacer, TableStyle

def generate_bl_pdf(livraison):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # En-tête
    elements.append(Paragraph(
        f"<b>BON DE LIVRAISON N°{livraison.numero_bl}</b>", 
        styles['Title']
    ))
    elements.append(Spacer(1, 20))

    # Informations principales
    info_data = [
        ["Date de livraison", livraison.date_livraison.strftime("%d/%m/%Y %H:%M")],
        ["Commande associée", livraison.commande.numero_commande],
        ["Fournisseur", livraison.commande.fournisseur.raison_sociale],
        ["Service destinataire", livraison.commande.service_destination.name],
    ]

    info_table = Table(info_data, colWidths=[150, 300])
    info_table.setStyle(
        TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN',   (0, 0), (-1, -1), 'TOP'),
        ])
    )
    elements.append(info_table)
    elements.append(Spacer(1, 30))

    # Tableau des articles
    articles_header = ["Produit", "Quantité", "Prix unitaire", "Lot", "Péremption"]
    articles_data = [articles_header]

    for achat in livraison.achats.all():
        articles_data.append([
            achat.produit.nom,
            str(achat.quantite_achetee),
            f"{achat.prix_unitaire} €",
            achat.numero_lot or "-",
            achat.date_peremption.strftime("%d/%m/%Y")
        ])

    articles_table = Table(articles_data, repeatRows=1)
    articles_table.setStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f8f9fa')),
        ('GRID', (0,0), (-1,-1), 1, colors.HexColor('#dee2e6')),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ALIGN', (2,0), (2,-1), 'RIGHT'),
        ('ALIGN', (4,0), (4,-1), 'CENTER'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8f9fa')])
    ])

    elements.append(Paragraph("<b>Articles livrés :</b>", styles['Heading2']))
    elements.append(Spacer(1, 10))
    elements.append(articles_table)

    doc.build(elements)
    buffer.seek(0)
    return File(buffer, name=f"BL_{livraison.numero_bl}.pdf")
