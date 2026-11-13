"""Sensors: one device for each account (house) on the login."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DaytonaConfigEntry, DaytonaCoordinator

USD = "USD"
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class UtilitySensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _average_bill(account: dict[str, Any]) -> float | None:
    amounts = [b["charges"] for b in account["bills"][:12] if b["charges"] is not None]
    return round(sum(amounts) / len(amounts), 2) if amounts else None


def _history(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "bills": [
            {"date": b["date"].isoformat(), "charges": b["charges"], "usage": b["usage"]} for b in account["bills"][:12]
        ]
    }


def _money(key: str, name: str, icon: str, **extra: Any) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        "icon": icon,
        "device_class": SensorDeviceClass.MONETARY,
        "native_unit_of_measurement": USD,
        "suggested_display_precision": 2,
        **extra,
    }


DESCRIPTIONS: tuple[UtilitySensorDescription, ...] = (
    UtilitySensorDescription(**_money("amount_due", "Amount due", "mdi:cash-clock"), value_fn=lambda a: a["amount_due"]),
    UtilitySensorDescription(
        **_money("current_charges", "Latest bill", "mdi:receipt-text"),
        value_fn=lambda a: a["current_charges"],
        attrs_fn=_history,
    ),
    UtilitySensorDescription(**_money("previous_balance", "Balance carried forward", "mdi:cash-minus"), value_fn=lambda a: a["previous_balance"]),
    UtilitySensorDescription(**_money("average_bill", "Average bill, last 12", "mdi:chart-line"), value_fn=_average_bill),
    UtilitySensorDescription(
        key="due_date", name="Payment due date", icon="mdi:calendar-alert",
        device_class=SensorDeviceClass.DATE, value_fn=lambda a: a["due_date"],
    ),
    UtilitySensorDescription(
        key="bill_date", name="Latest bill date", icon="mdi:calendar-check",
        device_class=SensorDeviceClass.DATE, value_fn=lambda a: a["bill_date"],
    ),
    UtilitySensorDescription(
        key="water_usage", name="Water used, latest bill", icon="mdi:water",
        native_unit_of_measurement="kgal", state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=2,
        value_fn=lambda a: a["usage"],
    ),
)

CHARGE_NAMES = {
    "water": "Water charge", "sewer": "Sewer charge", "garbage": "Garbage charge",
    "stormwater": "Stormwater charge", "tax": "Utility tax",
}


def _charge_description(code: str) -> UtilitySensorDescription:
    name = CHARGE_NAMES.get(code, f"{code.replace('_', ' ').title()} charge")
    return UtilitySensorDescription(
        **_money(f"charge_{code}", name, "mdi:cash"),
        value_fn=lambda a, c=code: a["charges"].get(c),
    )


async def async_setup_entry(hass: HomeAssistant, entry: DaytonaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    known: set[tuple[str, str]] = set()

    @callback
    def _add_missing() -> None:
        new: list[UtilitySensor] = []
        for account_id, account in coordinator.data.items():
            wanted = list(DESCRIPTIONS) + [_charge_description(code) for code in account["charges"]]
            for description in wanted:
                if (account_id, description.key) not in known:
                    known.add((account_id, description.key))
                    new.append(UtilitySensor(coordinator, account_id, description))
        if new:
            async_add_entities(new)

    _add_missing()
    # A new service on a later bill, or a new account on the login, gets its sensors without a restart.
    entry.async_on_unload(coordinator.async_add_listener(_add_missing))


class UtilitySensor(CoordinatorEntity[DaytonaCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: UtilitySensorDescription

    def __init__(self, coordinator: DaytonaCoordinator, account_id: str, description: UtilitySensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._account_id = account_id
        self._attr_unique_id = f"{DOMAIN}_{account_id}_{description.key}"
        account = coordinator.data[account_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, account_id)},
            name=f"Utilities {account['address']}",
            manufacturer="City of Daytona Beach",
            model="Utility account",
            configuration_url="https://cc.codb.us",
        )

    @property
    def _account(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get(self._account_id)

    @property
    def available(self) -> bool:
        return super().available and self._account is not None

    @property
    def native_value(self) -> Any:
        account = self._account
        if account is None:
            return None
        return self.entity_description.value_fn(account)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        account = self._account
        if account is None:
            return None
        attrs = {"status": account["status"]} if self.entity_description.key == "amount_due" else {}
        if self.entity_description.attrs_fn:
            attrs.update(self.entity_description.attrs_fn(account))
        return attrs or None
