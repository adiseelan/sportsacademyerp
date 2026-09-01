from django import forms
from django.conf import settings


class EmailLoginForm(forms.Form):
    email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(
            attrs={
                "autofocus": True,
                "autocomplete": "email",
                "inputmode": "email",
                "placeholder": "you@gmail.com",
            }
        ),
    )

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class OtpForm(forms.Form):
    code = forms.CharField(
        label="Verification code",
        strip=True,
        widget=forms.TextInput(
            attrs={
                "autofocus": True,
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "pattern": "[0-9]*",
                "maxlength": str(settings.OTP_LENGTH),
                "placeholder": "0" * settings.OTP_LENGTH,
            }
        ),
    )

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        if not code.isdigit() or len(code) != settings.OTP_LENGTH:
            raise forms.ValidationError(
                f"Enter the {settings.OTP_LENGTH}-digit code from your email."
            )
        return code
