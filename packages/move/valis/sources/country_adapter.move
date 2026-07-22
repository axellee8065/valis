/// Country adapter registry + capabilities (docs/05 §3.2).
/// Only holders of an active CountryAdapterCap may register properties.
module valis::country_adapter {
    use std::string::{Self, String};
    use sui::clock::Clock;
    use sui::event;
    use sui::table::{Self, Table};
    use valis::errors;

    /// Admin capability for the whole protocol.
    public struct ProtocolAdminCap has key, store {
        id: UID,
    }

    /// Capability granted to an approved country adapter.
    public struct CountryAdapterCap has key, store {
        id: UID,
        country_code: String, // ISO 3166-1 alpha-2, uppercase
        issued_at: u64,
    }

    /// Registry of active country adapters (shared object).
    /// A cap is "active" iff its ID is the registered one for its country —
    /// deactivation removes the entry, so revoked caps fail registry checks
    /// even though the owned object itself cannot be mutated by the admin.
    public struct AdapterRegistry has key {
        id: UID,
        adapters: Table<String, ID>, // country_code => cap_id
    }

    // === Events ===
    public struct AdapterRegistered has copy, drop {
        cap_id: ID,
        country_code: String,
    }

    public struct AdapterDeactivated has copy, drop {
        cap_id: ID,
        country_code: String,
    }

    // === Init ===
    fun init(ctx: &mut TxContext) {
        let admin = ProtocolAdminCap { id: object::new(ctx) };
        transfer::transfer(admin, ctx.sender());

        let registry = AdapterRegistry {
            id: object::new(ctx),
            adapters: table::new(ctx),
        };
        transfer::share_object(registry);
    }

    // === Entry: admin registers a new country adapter ===
    public entry fun register_adapter(
        _admin: &ProtocolAdminCap,
        registry: &mut AdapterRegistry,
        country_code: vector<u8>,
        recipient: address,
        clock: &Clock,
        ctx: &mut TxContext,
    ) {
        let cc = string::utf8(country_code);
        assert!(cc.length() == 2, errors::invalid_country());
        assert!(!registry.adapters.contains(cc), errors::property_exists());

        let cap = CountryAdapterCap {
            id: object::new(ctx),
            country_code: cc,
            issued_at: clock.timestamp_ms(),
        };
        let cap_id = object::id(&cap);
        registry.adapters.add(cc, cap_id);

        event::emit(AdapterRegistered { cap_id, country_code: cc });
        transfer::transfer(cap, recipient);
    }

    // === Entry: admin deactivates an adapter (registry-level revocation) ===
    public entry fun deactivate(
        _admin: &ProtocolAdminCap,
        registry: &mut AdapterRegistry,
        country_code: vector<u8>,
    ) {
        let cc = string::utf8(country_code);
        assert!(registry.adapters.contains(cc), errors::property_not_found());
        let cap_id = registry.adapters.remove(cc);
        event::emit(AdapterDeactivated { cap_id, country_code: cc });
    }

    // === Queries ===
    public fun country_code(cap: &CountryAdapterCap): &String { &cap.country_code }

    /// A cap is active iff the registry still maps its country to this cap's ID.
    public fun is_active(registry: &AdapterRegistry, cap: &CountryAdapterCap): bool {
        registry.adapters.contains(cap.country_code)
            && *registry.adapters.borrow(cap.country_code) == object::id(cap)
    }
}
