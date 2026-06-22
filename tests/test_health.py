"""Tests for liveness and readiness reporting."""

import unittest

from app.api.health import collect_readiness, liveness


class HealthEndpointTests(unittest.IsolatedAsyncioTestCase):
    def test_liveness_does_not_require_external_services(self):
        self.assertEqual(liveness(), {"status": "ok"})

    async def test_readiness_collects_successful_checks(self):
        services = await collect_readiness({"database": lambda: None})

        self.assertEqual(services, {"database": {"status": "ok"}})

    async def test_readiness_preserves_dependency_error(self):
        def fail() -> None:
            raise ConnectionError("service unavailable")

        services = await collect_readiness({"database": fail})

        self.assertEqual(services["database"]["status"], "error")
        self.assertIn("service unavailable", services["database"]["detail"])
