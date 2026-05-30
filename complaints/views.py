# complaints/views.py
from urllib import request

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views import View
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Complaint
from .forms import ComplaintForm
from .decorators import corporator_required


# ── CBV: Citizen complaint list ──────────────────────────
class ComplaintListView(LoginRequiredMixin, ListView):
    model               = Complaint
    template_name       = 'complaints/complaint_list.html'
    context_object_name = 'complaints'

    def get_queryset(self):
        # citizens see only their own complaints
        if self.request.user.role == 'corporator':
            return Complaint.objects.all()
        return Complaint.objects.filter(user=self.request.user)


# ── CBV: Complaint detail ────────────────────────────────
class ComplaintDetailView(LoginRequiredMixin, DetailView):
    model               = Complaint
    template_name       = 'complaints/complaint_detail.html'
    context_object_name = 'complaint'


# ── CBV: Create complaint ────────────────────────────────
class ComplaintCreateView(LoginRequiredMixin, View):

    def get(self, request):
        form = ComplaintForm()
        return render(request, 'complaints/complaint_form.html', {'form': form})

    def post(self, request):
        form = ComplaintForm(request.POST, request.FILES)
        if form.is_valid():
            complaint           = form.save(commit=False)
            complaint.user      = request.user
            complaint.latitude  = float(request.POST.get('latitude',  0.0))  # ← float()
            complaint.longitude = float(request.POST.get('longitude', 0.0))  # ← float()
            complaint.save()
            return redirect('complaint-list')
        return render(request, 'complaints/complaint_form.html', {'form': form})


# ── FBV: Corporator dashboard ────────────────────────────
@corporator_required
def corporator_dashboard(request):
    status_filter = request.GET.get('status', '')
    if status_filter:
        complaints = Complaint.objects.filter(status=status_filter)
    else:
        complaints = Complaint.objects.all()

    return render(request, 'complaints/corporator_dashboard.html', {
        'complaints':    complaints,
        'status_filter': status_filter,
        'total':         Complaint.objects.count(),
        'submitted':     Complaint.objects.filter(status='submitted').count(),
        'seen':          Complaint.objects.filter(status='seen').count(),
        'resolved':      Complaint.objects.filter(status='resolved').count(),
    })


# ── FBV: Update status ───────────────────────────────────
@corporator_required
def update_status(request, pk):
    complaint = get_object_or_404(Complaint, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in ['submitted', 'seen', 'resolved']:
            complaint.status = new_status
            complaint.save()
            messages.success(request, f'Status updated to {new_status}.')
    return redirect('corporator-dashboard')

# complaints/views.py — add these imports at the top
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as drf_status
from rest_framework.permissions import IsAuthenticated
from .serializers import ComplaintSerializer


# ── API: List all complaints ─────────────────────────────
class ComplaintListAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role == 'corporator':
            complaints = Complaint.objects.all()
        else:
            complaints = Complaint.objects.filter(user=request.user)

        serializer = ComplaintSerializer(
            complaints, many=True, context={'request': request}
        )
        return Response(serializer.data)


# ── API: Single complaint detail ─────────────────────────
class ComplaintDetailAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        complaint  = get_object_or_404(Complaint, pk=pk)
        serializer = ComplaintSerializer(
            complaint, context={'request': request}
        )
        return Response(serializer.data)

    def patch(self, request, pk):
        # only corporators can update status via API
        if request.user.role != 'corporator':
            return Response(
                {'error': 'Only corporators can update status.'},
                status=drf_status.HTTP_403_FORBIDDEN
            )
        complaint  = get_object_or_404(Complaint, pk=pk)
        new_status = request.data.get('status')
        if new_status not in ['submitted', 'seen', 'resolved']:
            return Response(
                {'error': 'Invalid status.'},
                status=drf_status.HTTP_400_BAD_REQUEST
            )
        complaint.status = new_status
        complaint.save()
        return Response({'message': f'Status updated to {new_status}.'})