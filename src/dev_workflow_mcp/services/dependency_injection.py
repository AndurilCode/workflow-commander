"""Simple dependency injection framework for configuration service."""

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class DependencyInjectionError(Exception):
    """Exception raised when dependency injection fails."""

    pass


class ServiceRegistry:
    """Registry for managing service dependencies."""

    def __init__(self):
        """Initialize the service registry."""
        self._services: dict[type[Any], Any] = {}
        self._factories: dict[type[Any], Callable[[], Any]] = {}
        self._singletons: dict[type[Any], Any] = {}

    def register_service(self, service_type: type[T], service_instance: T) -> None:
        """Register a service instance.

        Args:
            service_type: The service type/interface
            service_instance: The service instance
        """
        self._services[service_type] = service_instance

    def register_factory(
        self, service_type: type[T], factory_func: Callable[[], T]
    ) -> None:
        """Register a factory function for creating service instances.

        Args:
            service_type: The service type/interface
            factory_func: Factory function that creates service instances
        """
        self._factories[service_type] = factory_func

    def register_singleton(
        self, service_type: type[T], factory_func: Callable[[], T]
    ) -> None:
        """Register a singleton service with lazy initialization.

        Args:
            service_type: The service type/interface
            factory_func: Factory function that creates the singleton instance
        """
        self._factories[service_type] = factory_func
        # Mark as singleton by adding to singletons dict with None value
        self._singletons[service_type] = None

    def get_service(self, service_type: type[T]) -> T:
        """Get a service instance.

        Args:
            service_type: The service type/interface

        Returns:
            Service instance

        Raises:
            DependencyInjectionError: If service is not registered
        """
        # Check for direct service registration
        if service_type in self._services:
            return self._services[service_type]

        # Check for singleton
        if service_type in self._singletons:
            if self._singletons[service_type] is None:
                # Lazy initialization of singleton
                if service_type not in self._factories:
                    raise DependencyInjectionError(
                        f"No factory registered for singleton service: {service_type}"
                    )
                self._singletons[service_type] = self._factories[service_type]()
            return self._singletons[service_type]

        # Check for factory
        if service_type in self._factories:
            return self._factories[service_type]()

        raise DependencyInjectionError(f"Service not registered: {service_type}")

    def has_service(self, service_type: type[T]) -> bool:
        """Check if a service is registered.

        Args:
            service_type: The service type/interface

        Returns:
            True if service is registered, False otherwise
        """
        return (
            service_type in self._services
            or service_type in self._factories
            or service_type in self._singletons
        )

    def clear_registry(self) -> None:
        """Clear all registered services (primarily for testing)."""
        self._services.clear()
        self._factories.clear()
        self._singletons.clear()


# Global service registry
_service_registry = ServiceRegistry()


def get_service_registry() -> ServiceRegistry:
    """Get the global service registry.

    Returns:
        ServiceRegistry instance
    """
    return _service_registry


def register_service(service_type: type[T], service_instance: T) -> None:
    """Register a service instance in the global registry.

    Args:
        service_type: The service type/interface
        service_instance: The service instance
    """
    _service_registry.register_service(service_type, service_instance)


def register_factory(service_type: type[T], factory_func: Callable[[], T]) -> None:
    """Register a factory function in the global registry.

    Args:
        service_type: The service type/interface
        factory_func: Factory function that creates service instances
    """
    _service_registry.register_factory(service_type, factory_func)


def register_singleton(service_type: type[T], factory_func: Callable[[], T]) -> None:
    """Register a singleton service in the global registry.

    Args:
        service_type: The service type/interface
        factory_func: Factory function that creates the singleton instance
    """
    _service_registry.register_singleton(service_type, factory_func)


def get_service(service_type: type[T]) -> T:
    """Get a service instance from the global registry.

    Args:
        service_type: The service type/interface

    Returns:
        Service instance

    Raises:
        DependencyInjectionError: If service is not registered
    """
    return _service_registry.get_service(service_type)


def has_service(service_type: type[T]) -> bool:
    """Check if a service is registered in the global registry.

    Args:
        service_type: The service type/interface

    Returns:
        True if service is registered, False otherwise
    """
    return _service_registry.has_service(service_type)


def clear_registry() -> None:
    """Clear all registered services (primarily for testing)."""
    _service_registry.clear_registry()


# Dependency injection decorators
def inject_service(service_type: type[T]) -> Callable[[Callable], Callable]:
    """Decorator to inject a service into a function or method.

    Args:
        service_type: The service type to inject

    Returns:
        Decorator function
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            # Inject the service as the first argument
            service = get_service(service_type)
            return func(service, *args, **kwargs)

        return wrapper

    return decorator


def inject_config_service(func: Callable) -> Callable:
    """Convenience decorator to inject the configuration service.

    Args:
        func: Function to decorate

    Returns:
        Decorated function
    """

    def wrapper(*args, **kwargs):
        from .config_service import get_configuration_service

        config_service = get_configuration_service()
        return func(config_service, *args, **kwargs)

    return wrapper
