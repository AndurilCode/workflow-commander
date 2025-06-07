"""Tests for dependency injection framework."""

import pytest

from src.dev_workflow_mcp.services.dependency_injection import (
    DependencyInjectionError,
    ServiceRegistry,
    clear_registry,
    get_service,
    get_service_registry,
    has_service,
    inject_config_service,
    inject_service,
    register_factory,
    register_service,
    register_singleton,
)


class MockService:
    """Mock service for testing."""

    def __init__(self, value: str = "test"):
        self.value = value

    def get_value(self) -> str:
        return self.value


class MockProtocol:
    """Mock protocol for testing."""

    def get_value(self) -> str: ...


class TestServiceRegistry:
    """Test ServiceRegistry class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.registry = ServiceRegistry()

    def test_register_and_get_service(self):
        """Test registering and retrieving a service instance."""
        service = MockService("direct_service")
        self.registry.register_service(MockService, service)

        retrieved = self.registry.get_service(MockService)
        assert retrieved is service
        assert retrieved.get_value() == "direct_service"

    def test_register_and_get_factory(self):
        """Test registering and using a factory function."""

        def create_service() -> MockService:
            return MockService("factory_service")

        self.registry.register_factory(MockService, create_service)

        # Each call should create a new instance
        service1 = self.registry.get_service(MockService)
        service2 = self.registry.get_service(MockService)

        assert service1 is not service2
        assert service1.get_value() == "factory_service"
        assert service2.get_value() == "factory_service"

    def test_register_and_get_singleton(self):
        """Test registering and using a singleton service."""

        def create_service() -> MockService:
            return MockService("singleton_service")

        self.registry.register_singleton(MockService, create_service)

        # Multiple calls should return the same instance
        service1 = self.registry.get_service(MockService)
        service2 = self.registry.get_service(MockService)

        assert service1 is service2
        assert service1.get_value() == "singleton_service"

    def test_has_service(self):
        """Test checking if a service is registered."""
        # No service registered
        assert self.registry.has_service(MockService) is False

        # Register direct service
        service = MockService()
        self.registry.register_service(MockService, service)
        assert self.registry.has_service(MockService) is True

        # Clear and register factory
        self.registry.clear_registry()
        self.registry.register_factory(MockService, lambda: MockService())
        assert self.registry.has_service(MockService) is True

        # Clear and register singleton
        self.registry.clear_registry()
        self.registry.register_singleton(MockService, lambda: MockService())
        assert self.registry.has_service(MockService) is True

    def test_get_service_not_registered(self):
        """Test getting a service that is not registered."""
        with pytest.raises(DependencyInjectionError, match="Service not registered"):
            self.registry.get_service(MockService)

    def test_singleton_without_factory(self):
        """Test singleton registration without factory."""
        # Manually set up invalid singleton state
        self.registry._singletons[MockService] = None

        with pytest.raises(
            DependencyInjectionError,
            match="No factory registered for singleton service",
        ):
            self.registry.get_service(MockService)

    def test_clear_registry(self):
        """Test clearing all registered services."""
        # Register services of all types
        self.registry.register_service(MockService, MockService("direct"))
        self.registry.register_factory(str, lambda: "factory")
        self.registry.register_singleton(int, lambda: 42)

        # Verify services are registered
        assert self.registry.has_service(MockService) is True
        assert self.registry.has_service(str) is True
        assert self.registry.has_service(int) is True

        # Clear registry
        self.registry.clear_registry()

        # Verify services are no longer registered
        assert self.registry.has_service(MockService) is False
        assert self.registry.has_service(str) is False
        assert self.registry.has_service(int) is False

    def test_service_priority(self):
        """Test service resolution priority (direct > singleton > factory)."""
        # Register all types for same service
        direct_service = MockService("direct")
        self.registry.register_service(MockService, direct_service)
        self.registry.register_singleton(MockService, lambda: MockService("singleton"))
        self.registry.register_factory(MockService, lambda: MockService("factory"))

        # Direct service should have priority
        retrieved = self.registry.get_service(MockService)
        assert retrieved is direct_service
        assert retrieved.get_value() == "direct"


class TestGlobalFunctions:
    """Test global dependency injection functions."""

    def setup_method(self):
        """Set up test fixtures."""
        clear_registry()

    def teardown_method(self):
        """Clean up after tests."""
        clear_registry()

    def test_get_service_registry(self):
        """Test getting the global service registry."""
        registry = get_service_registry()
        assert isinstance(registry, ServiceRegistry)

        # Should return the same instance
        registry2 = get_service_registry()
        assert registry is registry2

    def test_register_and_get_service(self):
        """Test global service registration and retrieval."""
        service = MockService("global_service")
        register_service(MockService, service)

        retrieved = get_service(MockService)
        assert retrieved is service
        assert retrieved.get_value() == "global_service"

    def test_register_and_get_factory(self):
        """Test global factory registration and retrieval."""

        def create_service() -> MockService:
            return MockService("global_factory")

        register_factory(MockService, create_service)

        service1 = get_service(MockService)
        service2 = get_service(MockService)

        assert service1 is not service2
        assert service1.get_value() == "global_factory"
        assert service2.get_value() == "global_factory"

    def test_register_and_get_singleton(self):
        """Test global singleton registration and retrieval."""

        def create_service() -> MockService:
            return MockService("global_singleton")

        register_singleton(MockService, create_service)

        service1 = get_service(MockService)
        service2 = get_service(MockService)

        assert service1 is service2
        assert service1.get_value() == "global_singleton"

    def test_has_service(self):
        """Test global has_service function."""
        assert has_service(MockService) is False

        register_service(MockService, MockService())
        assert has_service(MockService) is True

    def test_clear_registry(self):
        """Test global clear_registry function."""
        register_service(MockService, MockService())
        assert has_service(MockService) is True

        clear_registry()
        assert has_service(MockService) is False


class TestDecorators:
    """Test dependency injection decorators."""

    def setup_method(self):
        """Set up test fixtures."""
        clear_registry()

    def teardown_method(self):
        """Clean up after tests."""
        clear_registry()

    def test_inject_service_decorator(self):
        """Test @inject_service decorator."""
        # Register service
        service = MockService("injected_service")
        register_service(MockService, service)

        # Define function with injection
        @inject_service(MockService)
        def test_function(injected_service: MockService, additional_arg: str) -> str:
            return f"{injected_service.get_value()}:{additional_arg}"

        # Call function - service should be automatically injected
        result = test_function("extra")
        assert result == "injected_service:extra"

    def test_inject_service_decorator_service_not_found(self):
        """Test @inject_service decorator when service is not registered."""

        @inject_service(MockService)
        def test_function(injected_service: MockService) -> str:
            return injected_service.get_value()

        with pytest.raises(DependencyInjectionError):
            test_function()

    def test_inject_config_service_decorator(self):
        """Test @inject_config_service decorator."""
        # Initialize configuration service
        from src.dev_workflow_mcp.services.config_service import (
            ConfigurationService,
            initialize_configuration_service,
            reset_configuration_service,
        )

        try:
            config_service = initialize_configuration_service()

            @inject_config_service
            def test_function(config: ConfigurationService, additional_arg: str) -> str:
                server_config = config.get_server_config()
                return f"{server_config.cache_collection_name}:{additional_arg}"

            result = test_function("extra")
            assert result == "workflow_states:extra"

        finally:
            reset_configuration_service()

    def test_inject_config_service_decorator_not_initialized(self):
        """Test @inject_config_service decorator when service is not initialized."""
        from src.dev_workflow_mcp.services.config_service import (
            reset_configuration_service,
        )

        reset_configuration_service()

        @inject_config_service
        def test_function(config) -> str:
            return "should not reach here"

        with pytest.raises(Exception):  # Should raise ConfigurationError
            test_function()


class TestIntegrationWithConfigurationService:
    """Test integration between dependency injection and configuration service."""

    def setup_method(self):
        """Set up test fixtures."""
        clear_registry()

    def teardown_method(self):
        """Clean up after tests."""
        clear_registry()
        from src.dev_workflow_mcp.services.config_service import (
            reset_configuration_service,
        )

        reset_configuration_service()

    def test_register_configuration_service_as_singleton(self):
        """Test registering configuration service as singleton."""
        from src.dev_workflow_mcp.services.config_service import (
            ConfigurationService,
            ConfigurationServiceProtocol,
        )

        def create_config_service() -> ConfigurationService:
            return ConfigurationService()

        register_singleton(ConfigurationServiceProtocol, create_config_service)

        # Get service multiple times
        service1 = get_service(ConfigurationServiceProtocol)
        service2 = get_service(ConfigurationServiceProtocol)

        # Should be the same instance
        assert service1 is service2
        assert isinstance(service1, ConfigurationService)

    def test_dependency_injection_with_configuration_models(self):
        """Test dependency injection with configuration models."""
        from src.dev_workflow_mcp.services.config_service import ServerConfiguration

        # Register server configuration
        server_config = ServerConfiguration(cache_max_results=100)
        register_service(ServerConfiguration, server_config)

        @inject_service(ServerConfiguration)
        def get_cache_max_results(config: ServerConfiguration) -> int:
            return config.cache_max_results

        result = get_cache_max_results()
        assert result == 100
