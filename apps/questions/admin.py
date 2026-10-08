"""Administration des questions, lots et séries (§8.2, §8.4)."""
from django import forms
from django.contrib import admin

from apps.commun.admin import AdminDuClient, ConsultationSeule, InlineDuClient, organisations_visibles
from apps.questions import services
from apps.questions.models import Lot, PassageCoranique, Question, QuestionDeSerie, Serie


class PassageInline(InlineDuClient):
    model = PassageCoranique
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Question)
class QuestionAdmin(AdminDuClient):
    """Création d'énoncés libres. Les passages coraniques se créent par ``creer_question_passage`` :
    le service vérifie les références dans le corpus avant d'écrire (REC-05)."""

    list_display = ("__str__", "type", "version_corpus", "organisation")
    list_filter = ("type", "organisation")
    search_fields = ("enonce",)
    inlines = [PassageInline]

    def get_inlines(self, request, obj):
        return [PassageInline] if obj else []  # rien à afficher à la création

    def get_readonly_fields(self, request, obj=None):
        return ("type", "version_corpus") if obj else ()

    def get_changeform_initial_data(self, request):
        return {"type": Question.Type.ENONCE}

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "type" and "choices" not in kwargs:
            kwargs["choices"] = [(Question.Type.ENONCE, "Énoncé")]
        return super().formfield_for_choice_field(db_field, request, **kwargs)


@admin.register(Lot)
class LotAdmin(ConsultationSeule):
    list_display = ("epreuve", "organisation")


class QuestionDeSerieInline(InlineDuClient):
    model = QuestionDeSerie
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class SerieForm(forms.ModelForm):
    questions = forms.ModelMultipleChoiceField(
        queryset=Question.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Cochez exactement P questions. Elles sont rangées dans l'ordre de leur création.",
    )

    class Meta:
        model = Serie
        fields = ("lot",)


@admin.register(Serie)
class SerieAdmin(AdminDuClient):
    """Une série se compose par ``composer_serie`` (RM-22, RM-23) ; elle ne se modifie pas ensuite."""

    list_display = ("__str__", "lot", "organisation")
    list_filter = ("lot__epreuve",)
    form = SerieForm
    inlines = [QuestionDeSerieInline]

    def get_inlines(self, request, obj):
        return [QuestionDeSerieInline] if obj else []

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj is None:
            visibles = organisations_visibles(request.user)
            queryset = Question.objects.order_by("cree_le")
            if visibles is not None:
                queryset = queryset.filter(organisation_id__in=visibles)
            form.base_fields["questions"].queryset = queryset
        return form

    def get_fields(self, request, obj=None):
        return ("lot", "questions") if obj is None else ("lot", "numero")

    def get_readonly_fields(self, request, obj=None):
        return ("lot", "numero") if obj else ()

    def has_change_permission(self, request, obj=None):
        return False if obj else super().has_change_permission(request, obj)

    def save_model(self, request, obj, form, change):
        def composer():
            serie = services.composer_serie(obj.lot, form.cleaned_data["questions"].order_by("cree_le"))
            obj.__dict__.update(serie.__dict__)  # l'objet affiché est celui enregistré

        self.executer_metier(request, composer)
