from django.contrib.auth.decorators import permission_required
from django.shortcuts import render
from .models import Documents

@permission_required('documents.view_document', raise_exception=True)
def liste_documents(request):
    documents = Documents.objects.all()
    return render(request, 'liste_documents.html', {'documents': documents})
