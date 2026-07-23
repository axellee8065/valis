/// On-chain property objects, 1:1 with real-world assets (docs/05 §3.3).
///
/// Coordinates use OFFSET-ENCODED u64 (Move has no signed integers):
///     lat_e7 = (latitude_deg  +  90) * 1e7   — range [0, 180e7]
///     lng_e7 = (longitude_deg + 180) * 1e7   — range [0, 360e7]
module valis::property_registry {
    use std::string::{Self, String};
    use sui::clock::Clock;
    use sui::dynamic_field as df;
    use sui::event;
    use sui::table::{Self, Table};
    use valis::country_adapter::{Self, AdapterRegistry, CountryAdapterCap};
    use valis::errors;

    const LAT_MAX_E7: u64 = 1_800_000_000; //  +90° with +90 offset
    const LNG_MAX_E7: u64 = 3_600_000_000; // +180° with +180 offset

    /// A property registered in the protocol.
    /// `global_id` is sha256("{country_code}:{local_id_canonical}") computed
    /// off-chain — deterministic dedup across the protocol.
    public struct Property has key, store {
        id: UID,
        global_id: vector<u8>, // 32 bytes sha256
        country_code: String,
        local_id_canonical: String,
        property_type: String, // enum as string, extensible for UAE
        registered_at: u64,
        registered_by: address,
        // Dynamic fields: b"geo" => GeoData, b"metrics" => PropertyMetrics
    }

    public struct GeoData has store, drop {
        lat_e7: u64, // offset-encoded, see module doc
        lng_e7: u64,
        admin_level_1: String,
        admin_level_2: String,
        admin_level_3: String,
    }

    public struct PropertyMetrics has store, drop {
        net_area_sqm_x100: u64,
        built_year: u16,
        floors_total: u16,
        floor_number: u16,
    }

    /// Shared index: global_id -> Property object ID. Prevents duplicates.
    public struct PropertyIndex has key {
        id: UID,
        by_global_id: Table<vector<u8>, ID>,
    }

    // === Events ===
    public struct PropertyRegistered has copy, drop {
        property_id: ID,
        global_id: vector<u8>,
        country_code: String,
    }

    // === Init ===
    fun init(ctx: &mut TxContext) {
        let index = PropertyIndex {
            id: object::new(ctx),
            by_global_id: table::new(ctx),
        };
        transfer::share_object(index);
    }

    // === Entry: adapter registers a property ===
    public fun register(
        adapter_cap: &CountryAdapterCap,
        adapter_registry: &AdapterRegistry,
        index: &mut PropertyIndex,
        global_id: vector<u8>,
        local_id_canonical: vector<u8>,
        property_type: vector<u8>,
        lat_e7: u64,
        lng_e7: u64,
        admin_1: vector<u8>,
        admin_2: vector<u8>,
        admin_3: vector<u8>,
        net_area_sqm_x100: u64,
        built_year: u16,
        floors_total: u16,
        floor_number: u16,
        clock: &Clock,
        ctx: &mut TxContext,
    ) {
        let prop = create(
            adapter_cap,
            adapter_registry,
            index,
            global_id,
            local_id_canonical,
            property_type,
            lat_e7,
            lng_e7,
            admin_1,
            admin_2,
            admin_3,
            net_area_sqm_x100,
            built_year,
            floors_total,
            floor_number,
            clock,
            ctx,
        );
        share(prop);
    }

    /// Package-internal create returning the unshared object — lets
    /// `valis::batch` attach an attestation before sharing, in one tx.
    public(package) fun create(
        adapter_cap: &CountryAdapterCap,
        adapter_registry: &AdapterRegistry,
        index: &mut PropertyIndex,
        global_id: vector<u8>,
        local_id_canonical: vector<u8>,
        property_type: vector<u8>,
        lat_e7: u64,
        lng_e7: u64,
        admin_1: vector<u8>,
        admin_2: vector<u8>,
        admin_3: vector<u8>,
        net_area_sqm_x100: u64,
        built_year: u16,
        floors_total: u16,
        floor_number: u16,
        clock: &Clock,
        ctx: &mut TxContext,
    ): Property {
        assert!(
            country_adapter::is_active(adapter_registry, adapter_cap),
            errors::adapter_inactive(),
        );
        assert!(global_id.length() == 32, errors::invalid_valuation());
        assert!(!index.by_global_id.contains(global_id), errors::property_exists());
        assert!(lat_e7 <= LAT_MAX_E7 && lng_e7 <= LNG_MAX_E7, errors::invalid_valuation());

        let country_code = *country_adapter::country_code(adapter_cap);
        let now = clock.timestamp_ms();

        let mut prop = Property {
            id: object::new(ctx),
            global_id,
            country_code,
            local_id_canonical: string::utf8(local_id_canonical),
            property_type: string::utf8(property_type),
            registered_at: now,
            registered_by: ctx.sender(),
        };

        df::add(&mut prop.id, b"geo", GeoData {
            lat_e7,
            lng_e7,
            admin_level_1: string::utf8(admin_1),
            admin_level_2: string::utf8(admin_2),
            admin_level_3: string::utf8(admin_3),
        });

        df::add(&mut prop.id, b"metrics", PropertyMetrics {
            net_area_sqm_x100,
            built_year,
            floors_total,
            floor_number,
        });

        let prop_id = object::id(&prop);
        index.by_global_id.add(global_id, prop_id);

        event::emit(PropertyRegistered {
            property_id: prop_id,
            global_id,
            country_code,
        });

        prop
    }

    /// Shared so anyone can reference it when attaching attestations.
    public(package) fun share(prop: Property) {
        transfer::share_object(prop);
    }

    // === Queries ===
    public fun global_id(p: &Property): &vector<u8> { &p.global_id }
    public fun country_code(p: &Property): &String { &p.country_code }
    public fun uid(p: &Property): &UID { &p.id }

    public fun contains(index: &PropertyIndex, global_id: vector<u8>): bool {
        index.by_global_id.contains(global_id)
    }

    public fun lookup(index: &PropertyIndex, global_id: vector<u8>): ID {
        assert!(index.by_global_id.contains(global_id), errors::property_not_found());
        *index.by_global_id.borrow(global_id)
    }
}
