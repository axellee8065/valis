#[test_only]
module valis::errors_tests {
    use valis::errors;

    #[test]
    fun error_codes_are_stable() {
        // Error codes are part of the public ABI — partners match on them.
        // Changing any of these is a breaking change.
        assert!(errors::not_authorized() == 1);
        assert!(errors::invalid_country() == 2);
        assert!(errors::property_exists() == 3);
        assert!(errors::property_not_found() == 4);
        assert!(errors::attestation_expired() == 5);
        assert!(errors::invalid_confidence() == 6);
        assert!(errors::adapter_inactive() == 7);
        assert!(errors::invalid_valuation() == 8);
        assert!(errors::revoked() == 9);
    }
}
// Full object-flow tests (registration, issuance, feed, revocation, expiry
// boundaries — docs/05 §6.1) are the M5 deliverable and use sui::test_scenario.
