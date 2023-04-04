from django.test import TestCase, SimpleTestCase
from django.contrib.auth import get_user_model
from .settings import flash_settings
from django.template import loader
from django.utils import timezone
from django.conf import settings
from django.urls import reverse
from django.core import mail

from rest_framework.test import APITestCase
from rest_framework import status

from .settings import settings as flash_settings_module
from .models import ActivationToken

import string


User = get_user_model()


class AppSettingsTestCase(SimpleTestCase):
    def test_loading_user_settings_correctly(self):
        user_settings = getattr(settings, "FLASH_SETTINGS", {})
        for setting, value in user_settings.items():
            self.assertEqual(value, getattr(flash_settings, setting))

    def test_loading_default_settings_correctly(self):
        default_settings = getattr(flash_settings_module, "DEFAULT_SETTINGS", {})
        user_settings = getattr(settings, "FLASH_SETTINGS", {})
        for setting, value in default_settings.items():
            if setting not in user_settings.keys():
                self.assertEqual(value, getattr(flash_settings, setting))


class ActivationTokenTestCase(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="testUser",
            email="testemail@test.com",
            password="testpassword123",
        )
        self.user.save()
        self.token = ActivationToken.objects.create(user=self.user)
        self.characters = string.ascii_letters + string.digits

    def test_generate_token(self):
        self.assertEqual(self.token.token, "")

        self.token.generate_token()
        self.token.save()

        self.assertEquals(type(self.token.token), str)
        self.assertEqual(len(self.token.token), 55)

        for char in self.token.token:
            self.assertIn(char, self.characters)

    def test_set_expiration_date(self):
        self.assertEqual(self.token.expiration_date, None)

        self.token.set_expiration_date()
        self.token.save()

        self.assertLess(
            self.token.expiration_date,
            timezone.now()
            + flash_settings.ACTIVATION_TOKEN_LIFETIME
            + timezone.timedelta(seconds=10),
        )
        self.assertGreater(
            self.token.expiration_date,
            timezone.now()
            + flash_settings.ACTIVATION_TOKEN_LIFETIME
            - timezone.timedelta(seconds=10),
        )

    def test_expired_property_false(self):
        self.token.set_expiration_date()
        self.token.save()
        self.assertEqual(self.token.expired, False)

    def test_expired_property_true(self):
        self.token.expiration_date = timezone.now() - timezone.timedelta(seconds=5)
        self.token.save()
        self.assertEqual(self.token.expired, True)


class RegisterTestCase(APITestCase):
    def setUp(self) -> None:
        self.valid_data = {
            "username": "testUser",
            "email": "testemail@test.com",
            "password": "testpassword123",
            "password2": "testpassword123",
        }
        self.invalid_passwords_data = {
            "username": "testUser",
            "email": "testemail@test.com",
            "password": "testpassword123",
            "password2": "testpassword321",
        }
        self.existing_email_data = {
            "username": "testUser2",
            "email": "testemail@test.com",
            "password": "test2password123",
            "password2": "test2password123",
        }
        self.existing_username_data = {
            "username": "testUser",
            "email": "testemail2@test.com",
            "password": "test2password123",
            "password2": "test2password123",
        }
        self.url = reverse("sign_up")

    def test_register_user(self):
        response = self.client.post(self.url, data=self.valid_data)

        self.assertEquals(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.first().username, "testUser")
        self.assertEqual(User.objects.first().email, "testemail@test.com")

        if flash_settings.ACTIVATE_ACCOUNT:
            self.assertEqual(User.objects.first().is_active, False)
        else:
            self.assertEqual(User.objects.first().is_active, True)

    def test_register_user_invalid_data(self):
        response = self.client.post(self.url, data=self.invalid_passwords_data)

        self.assertEquals(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.count(), 0)

    def test_email_exists(self):
        self.client.post(self.url, data=self.valid_data)
        response = self.client.post(self.url, data=self.existing_email_data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.count(), 1)

    def test_username_exists(self):
        self.client.post(self.url, data=self.valid_data)
        response = self.client.post(self.url, data=self.existing_username_data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.count(), 1)

    if flash_settings.ACTIVATE_ACCOUNT:

        def test_email_token_generated(self):
            self.client.post(self.url, data=self.valid_data)

            token = ActivationToken.objects.first()

            self.assertEqual(ActivationToken.objects.count(), 1)
            self.assertEqual(token.user.username, "testUser")
            self.assertEqual(len(token.token), 55)
            self.assertLess(
                token.expiration_date,
                timezone.now()
                + flash_settings.ACTIVATION_TOKEN_LIFETIME
                + timezone.timedelta(seconds=10),
            )
            self.assertGreater(
                token.expiration_date,
                timezone.now()
                + flash_settings.ACTIVATION_TOKEN_LIFETIME
                - timezone.timedelta(seconds=10),
            )

        def test_activation_email_send(self):
            self.client.post(self.url, data=self.valid_data)
            self.assertEqual(len(mail.outbox), 1)

            token = ActivationToken.objects.first()

            url = "http://testserver"
            url += reverse("activate", kwargs={"token_value": token.token})
            context = {
                "url": url,
                "username": "testUser",
                "host": "testserver",
            }

            template_html = loader.render_to_string(
                f"{flash_settings.ACTIVATION_EMAIL_TEMPLATE}.html", context
            )
            template_txt = loader.render_to_string(
                f"{flash_settings.ACTIVATION_EMAIL_TEMPLATE}.txt", context
            )

            email_html = mail.outbox[0].alternatives[0][0]
            email_txt = mail.outbox[0].body

            self.assertEqual(template_html, email_html)
            self.assertEqual(template_txt, email_txt)
