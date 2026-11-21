from django import forms


class CargaForm(forms.Form):
    archivo = forms.FileField(label="PDF escaneado", widget=forms.ClearableFileInput(attrs={"accept": "application/pdf"}))
    hoja_nombre = forms.CharField(label="Nombre de la paciente (como aparece en la hoja)", max_length=150)
    hoja_fecha_nacimiento = forms.DateField(label="Fecha de nacimiento", widget=forms.DateInput(attrs={"type": "date"}))
    hoja_folio_expediente = forms.CharField(label="Folio de expediente", max_length=30)
    folio_laboratorio = forms.CharField(label="Folio de laboratorio", max_length=30)
