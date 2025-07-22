from django.shortcuts import render
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy

class CustomLoginView(LoginView):
    template_name = 'authentication/login.html'  # path to your custom template

    def get_success_url(self):
        return reverse_lazy('parser:index')

    def form_valid(self, form):
        print("✅ Login successful for:", form.get_user())
        return super().form_valid(form)

    def form_invalid(self, form):
        print("❌ Login failed. Errors:", form.errors)
        return super().form_invalid(form)

class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('login')  # Redirect to login page after logout