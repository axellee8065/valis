/// One-transaction issuance pipeline (docs/05 §4.2).
///
/// register + issue + feed-publish bundled into a single call: the Property
/// is created, referenced by the freshly minted attestation, recorded on the
/// shared feed, and only then shared. Cuts batch issuance from 3 tx to 1 tx
/// per property.
module valis::batch {
    use sui::clock::Clock;
    use valis::attestation::{Self, IssuerCap};
    use valis::country_adapter::{AdapterRegistry, CountryAdapterCap};
    use valis::oracle_feed::{Self, ValuationFeed};
    use valis::property_registry::{Self, PropertyIndex};

    public fun register_and_attest(
        adapter_cap: &CountryAdapterCap,
        adapter_registry: &AdapterRegistry,
        index: &mut PropertyIndex,
        feed: &mut ValuationFeed,
        issuer_cap: &IssuerCap,
        // --- property ---
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
        // --- attestation ---
        value_usd_cents: u64,
        ci_lower_usd_cents: u64,
        ci_upper_usd_cents: u64,
        confidence_bps: u16,
        method: u8,
        model_id: vector<u8>,
        report_uri: vector<u8>,
        report_hash: vector<u8>,
        validity_ms: u64,
        clock: &Clock,
        recipient: address,
        ctx: &mut TxContext,
    ) {
        let prop = property_registry::create(
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
        let att = attestation::mint(
            issuer_cap,
            &prop,
            value_usd_cents,
            ci_lower_usd_cents,
            ci_upper_usd_cents,
            confidence_bps,
            method,
            model_id,
            report_uri,
            report_hash,
            validity_ms,
            clock,
            ctx,
        );
        oracle_feed::record(feed, &att, clock);
        property_registry::share(prop);
        transfer::public_transfer(att, recipient);
    }
}
