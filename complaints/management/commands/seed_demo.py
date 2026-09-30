# complaints/management/commands/seed_demo.py
"""
Populate a local database with believable demo data.

    python manage.py seed_demo
    python manage.py seed_demo --reset --complaints 60
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from complaints.models import Comment, Complaint, IssueType, Priority, Status, Upvote, Ward
from users.models import CustomUser, Role

WARDS = [
    (12, 'Kothrud'), (17, 'Aundh'), (24, 'Hadapsar'),
    (31, 'Kharadi'), (8, 'Shivajinagar'),
]

REPORTS = {
    'garbage': [
        ('Overflowing bin near the bus stop', 'The bin has not been emptied for over a week and is attracting stray dogs.'),
        ('Garbage dumped on the footpath', 'Construction debris left on the pavement, pedestrians are walking on the road.'),
        ('Missed collection on our lane', 'The collection van has skipped our lane three days running.'),
    ],
    'road': [
        ('Deep pothole at the junction', 'A two-wheeler skidded here yesterday evening. It fills with water when it rains.'),
        ('Road dug up and not restored', 'The cable work finished a month ago but the trench was never filled.'),
        ('Speed breaker with no markings', 'Unpainted and invisible at night.'),
    ],
    'water': [
        ('No supply since Tuesday', 'The entire building has been without water for three days.'),
        ('Pipeline leaking at the corner', 'Clean water running into the drain around the clock.'),
        ('Water pressure very low', 'Only a trickle reaches the upper floors in the morning.'),
    ],
    'streetlight': [
        ('Streetlight out for two weeks', 'The stretch between the school and the market is completely dark.'),
        ('Light flickers all night', 'It switches on and off every few seconds.'),
    ],
    'drainage': [
        ('Drain overflowing onto the road', 'Sewage on the road outside the clinic gate.'),
        ('Open manhole without a cover', 'Dangerous at night, someone will fall in.'),
    ],
    'stray': [('Aggressive stray dogs near the park', 'A pack has been chasing children on their way to school.')],
    'encroachment': [('Shop extended onto the footpath', 'Pedestrians are forced onto the carriageway.')],
    'other': [('Broken park bench', 'Splintered wood, unsafe to sit on.')],
}

CITIZEN_COMMENTS = [
    'Any update on this? It has been a while.',
    'This is still not fixed as of today.',
    'Thank you for looking into it.',
    'Happening again this morning.',
]
OFFICIAL_COMMENTS = [
    'Noted. A team has been assigned and will inspect this week.',
    'Work order raised with the department.',
    'Inspected on site today. Repair scheduled.',
    'This has been completed — please confirm.',
]


CITIZEN_NAMES = [
    ('Asha', 'Patil'), ('Rohit', 'Deshmukh'), ('Meera', 'Joshi'), ('Imran', 'Shaikh'),
    ('Kavita', 'Rane'), ('Sanjay', 'Kulkarni'), ('Neha', 'Gaikwad'), ('Vikram', 'Bhosale'),
]
CORPORATOR_NAMES = [
    ('Sunita', 'More'), ('Prakash', 'Jadhav'), ('Anil', 'Pawar'),
]


class Command(BaseCommand):
    help = 'Seed the database with demo wards, users and complaints.'

    def add_arguments(self, parser):
        parser.add_argument('--complaints', type=int, default=40, help='How many complaints to create.')
        parser.add_argument('--reset', action='store_true', help='Delete existing demo data first.')
        parser.add_argument('--seed', type=int, default=42, help='RNG seed, for repeatable output.')

    @transaction.atomic
    def handle(self, *args, **options):
        from django.conf import settings

        if not settings.DEBUG:
            raise CommandError('seed_demo refuses to run with DEBUG=False.')

        rng = random.Random(options['seed'])

        if options['reset']:
            Complaint.objects.all().delete()
            CustomUser.objects.filter(email__endswith='@example.com', is_superuser=False).delete()
            Ward.objects.all().delete()
            self.stdout.write('Cleared existing demo data.')

        wards = [Ward.objects.get_or_create(number=n, defaults={'name': name})[0] for n, name in WARDS]

        citizens = [
            self._make_user(f'{first.lower()}.{last.lower()}', first, last, Role.CITIZEN, rng.choice(wards))
            for first, last in CITIZEN_NAMES
        ]
        corporators = [
            self._make_user(f'{first.lower()}.{last.lower()}', first, last, Role.CORPORATOR, ward)
            for (first, last), ward in zip(CORPORATOR_NAMES, wards)
        ]
        # A city-wide officer (no ward) who can see and route everything.
        city_officer = self._make_user('ramesh.kale', 'Ramesh', 'Kale', Role.CORPORATOR, None)

        # Pune, roughly. Enough spread to make the map interesting.
        base_lat, base_lng = 18.5204, 73.8567
        now = timezone.now()
        created_count = 0

        for _ in range(options['complaints']):
            issue = rng.choice(list(REPORTS))
            title, description = rng.choice(REPORTS[issue])
            author = rng.choice(citizens)
            age = rng.randint(0, 90)

            complaint = Complaint.objects.create(
                user=author,
                issue_type=issue,
                title=title,
                description=description,
                latitude=round(base_lat + rng.uniform(-0.06, 0.06), 6),
                longitude=round(base_lng + rng.uniform(-0.06, 0.06), 6),
                ward=author.ward if rng.random() < 0.8 else rng.choice(wards),
                priority=rng.choices(
                    [Priority.LOW, Priority.NORMAL, Priority.HIGH, Priority.URGENT],
                    weights=[2, 6, 3, 1],
                )[0],
            )
            # auto_now_add ignores the value passed in, so backdate afterwards.
            filed_at = now - timedelta(days=age, hours=rng.randint(0, 23))
            Complaint.objects.filter(pk=complaint.pk).update(created_at=filed_at)
            complaint.refresh_from_db()

            complaint.history.create(changed_by=author, old_status='', new_status=Status.SUBMITTED,
                                     note='Complaint filed.')

            # Older complaints are more likely to have progressed.
            outcome = rng.choices(
                [Status.SUBMITTED, Status.SEEN, Status.IN_PROGRESS, Status.RESOLVED, Status.REJECTED],
                weights=[6, 3, 3, max(1, age // 8), 1],
            )[0]
            if outcome != Status.SUBMITTED:
                ward_staff = [c for c in corporators if c.ward_id == complaint.ward_id]
                handler = rng.choice(ward_staff) if ward_staff else city_officer
                path = {
                    Status.SEEN: [Status.SEEN],
                    Status.IN_PROGRESS: [Status.SEEN, Status.IN_PROGRESS],
                    Status.RESOLVED: [Status.SEEN, Status.IN_PROGRESS, Status.RESOLVED],
                    Status.REJECTED: [Status.SEEN, Status.REJECTED],
                }[outcome]
                previous = Status.SUBMITTED
                for step in path:
                    complaint.history.create(changed_by=handler, old_status=previous, new_status=step)
                    previous = step
                complaint.status = outcome
                complaint.assigned_to = handler
                complaint.resolved_at = (
                    filed_at + timedelta(days=rng.randint(1, max(2, age)))
                    if outcome in (Status.RESOLVED, Status.REJECTED) else None
                )
                complaint.save(update_fields=['status', 'assigned_to', 'resolved_at'])

            neighbours = [c for c in citizens if c.ward_id == complaint.ward_id and c != author]
            for voter in rng.sample(neighbours, rng.randint(0, len(neighbours))):
                Upvote.objects.get_or_create(complaint=complaint, user=voter)

            for _ in range(rng.randint(0, 3)):
                if rng.random() < 0.45 and complaint.assigned_to_id:
                    Comment.objects.create(complaint=complaint, author=complaint.assigned_to,
                                           body=rng.choice(OFFICIAL_COMMENTS))
                else:
                    Comment.objects.create(complaint=complaint, author=author,
                                           body=rng.choice(CITIZEN_COMMENTS))

            created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Seeded {len(wards)} wards, {len(citizens)} citizens, '
            f'{len(corporators)} corporators and {created_count} complaints.'
        ))
        self.stdout.write(
            f'Sign in as {citizens[0].username} (citizen), {corporators[0].username} '
            f'(ward corporator) or {city_officer.username} (city-wide officer) — password: demo1234'
        )

    def _make_user(self, username, first, last, role, ward):
        user, created = CustomUser.objects.get_or_create(
            username=username,
            defaults={
                'first_name': first,
                'last_name': last,
                'email': f'{username}@example.com',
                'role': role,
                'ward': ward,
                'email_verified': True,
            },
        )
        if created:
            user.set_password('demo1234')
            user.save(update_fields=['password'])
        return user
