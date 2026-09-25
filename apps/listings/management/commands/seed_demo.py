"""Seed demo users and listings for local development.

Usage::

    uv run python manage.py seed_demo
    uv run python manage.py seed_demo --count 80 --flush

The command is idempotent: listings are matched by title, so running it twice
will not duplicate data. Generated data is deterministic (fixed seed) and
clustered around real Lagos neighbourhoods so the radius search can be tested
with meaningful results.
"""

import random
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.enums import UserRole
from apps.accounts.models import User
from apps.accounts.services import UserService
from apps.listings.enums import ListingType
from apps.listings.models import Listing

ADMIN_CREDENTIALS = {"username": "admin", "password": "Admin123!"}
AGENT_CREDENTIALS = [
    {"username": "agent1", "password": "Agent123!"},
    {"username": "agent2", "password": "Agent123!"},
    {"username": "agent3", "password": "Agent123!"},
]

NEIGHBOURHOODS = [
    ("Lekki Phase 1", 6.4474, 3.4735),
    ("Lekki Phase 2", 6.4580, 3.4800),
    ("Victoria Island", 6.4281, 3.4219),
    ("Banana Island", 6.4340, 3.4370),
    ("Ikeja GRA", 6.5833, 3.3833),
    ("Ikeja Ogosa", 6.6010, 3.3510),
    ("Yaba", 6.5095, 3.3711),
    ("Maryland", 6.5545, 3.3780),
    ("Surulere", 6.5054, 3.3566),
    ("Ajah", 6.4698, 3.5852),
    ("Ikorodu", 6.4500, 3.4200),
    ("Agege", 6.6200, 3.3200),
]

TITLE_PREFIXES = [
    "Bright",
    "Modern",
    "Spacious",
    "Serviced",
    "Luxury",
    "Compact",
    "Executive",
    "Family",
]

TITLE_SUFFIXES = {
    ListingType.RENT: ["Apartment", "Duplex", "Studio", "Bungalow"],
    ListingType.SALE: ["Mansion", "Terrace", "Semi-detached", "Penthouse"],
    ListingType.SHORTLET: ["Shortlet", "Furnished Suite", "Service Apartment"],
}

PRICE_RANGES = {
    ListingType.RENT: (Decimal("150000"), Decimal("4500000")),
    ListingType.SALE: (Decimal("25000000"), Decimal("650000000")),
    ListingType.SHORTLET: (Decimal("2000000"), Decimal("15000000")),
}

STREETS = ["Ocean View", "Admiralty Way", "Awolowo Road", "Herbert Macaulay", "Bourdillon"]


class Command(BaseCommand):
    """Management command creating demo agents and property listings."""

    help = "Seed demo users and listings for local development."

    def add_arguments(self, parser) -> None:
        """Register command line arguments.

        Args:
            parser: The argument parser provided by Django.
        """
        parser.add_argument(
            "--count",
            type=int,
            default=40,
            help="Number of listings to create (default: 40).",
        )
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Hard delete existing listings and non admin users before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        """Create the demo data set.

        Args:
            *args: Unused positional args.
            **options: Parsed command options (``count``, ``flush``).

        Raises:
            CommandError: If ``--count`` is not a positive integer.
        """
        count = options["count"]
        if count < 1:
            raise CommandError("--count must be a positive integer.")

        if options["flush"]:
            deleted_listings = Listing.all_objects.all().hard_delete()
            deleted_users = User.all_objects.exclude(role=UserRole.ADMIN).hard_delete()
            self.stdout.write(
                self.style.WARNING(
                    f"Flushed {deleted_listings} listing(s) and {deleted_users} user(s)."
                )
            )

        admin = self._create_admin()
        agents = self._create_agents()

        rng = random.Random(42)
        created = 0
        for index in range(1, count + 1):
            agent = agents[(index - 1) % len(agents)]
            if self._create_listing(index, agent, rng):
                created += 1

        self.stdout.write(self.style.SUCCESS(f"Created {created} listing(s)."))
        self._print_credentials(admin)

    def _create_admin(self) -> User:
        """Create the demo admin user if it does not exist yet.

        Returns:
            The admin user.
        """
        existing = User.objects.filter(username=ADMIN_CREDENTIALS["username"]).first()
        if existing is not None:
            return existing

        admin = UserService.create(
            username=ADMIN_CREDENTIALS["username"],
            email="admin@elisting.test",
            password=ADMIN_CREDENTIALS["password"],
            role=UserRole.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.stdout.write(f"Created admin user '{admin.username}'.")
        return admin

    def _create_agents(self) -> list[User]:
        """Create the demo agent users if they do not exist yet.

        Returns:
            A list of agent users.
        """
        agents = []
        for index, credentials in enumerate(AGENT_CREDENTIALS, start=1):
            existing = User.objects.filter(username=credentials["username"]).first()
            if existing is not None:
                agents.append(existing)
                continue

            agent = UserService.create(
                username=credentials["username"],
                email=f"agent{index}@elisting.test",
                password=credentials["password"],
                role=UserRole.AGENT,
                first_name=f"Agent{index}",
                last_name="Demo",
            )
            self.stdout.write(f"Created agent user '{agent.username}'.")
            agents.append(agent)
        return agents

    def _create_listing(self, index: int, agent: User, rng: random.Random) -> bool:
        """Create a single deterministic listing.

        Args:
            index: 1-based index used to keep titles unique.
            agent: The owning agent.
            rng: Seeded random generator.

        Returns:
            ``True`` when a new listing was created, ``False`` when skipped.
        """
        listing_type = rng.choice(list(ListingType.values))
        neighbourhood, latitude, longitude = rng.choice(NEIGHBOURHOODS)
        bedrooms = rng.randint(1, 5)
        low, high = PRICE_RANGES[listing_type]
        price = Decimal(rng.randint(int(low), int(high))).quantize(Decimal("0.01"))
        title = (
            f"{rng.choice(TITLE_PREFIXES)} {bedrooms}-bedroom "
            f"{rng.choice(TITLE_SUFFIXES[listing_type])} in {neighbourhood} #{index}"
        )
        # Draw before the duplicate check so the random stream advances identically
        # whether or not the row already exists; otherwise titles shift between runs.
        location_name = f"{rng.choice(STREETS)}, {neighbourhood}"

        if Listing.all_objects.filter(title=title).exists():
            return False

        Listing.objects.create(
            title=title,
            price=price,
            type=listing_type,
            bedrooms=bedrooms,
            location_name=location_name,
            location=Point(longitude, latitude, srid=4326),
            agent=agent,
            created_by=agent,
            updated_by=agent,
        )
        return True

    def _print_credentials(self, admin: User) -> None:
        """Print the demo credentials to stdout.

        Args:
            admin: The admin user that was created or fetched.
        """
        self.stdout.write(self.style.SUCCESS("Demo credentials:"))
        self.stdout.write(
            f"  admin: {admin.username} / {ADMIN_CREDENTIALS['password']} (email: {admin.email})"
        )
        for credentials in AGENT_CREDENTIALS:
            self.stdout.write(
                f"  {credentials['username']}: {credentials['password']} "
                f"(email: {credentials['username']}@elisting.test)"
            )
        self.stdout.write(
            'Get a JWT: POST /api/v1/auth/token/ {"username": "agent1", "password": "Agent123!"}'
        )
