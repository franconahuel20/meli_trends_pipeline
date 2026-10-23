def test_reference_files_are_read_and_typed(reference_frames):
    brands = reference_frames["brands"]
    characters = reference_frames["characters"]
    subcategories = reference_frames["mercado_libre_subcat"]

    assert len(brands) > 8000 and brands["brand_str"].notna().all()
    assert str(brands["branded_int"].dtype) == "Int64"

    assert len(characters) > 1000 and characters["character_str"].notna().all()
    assert set(characters["twdc_int"].dropna().unique()) <= {0, 1}
    assert characters["comment_str"].notna().sum() > 0
    # Whitespace and non-breaking spaces from the spreadsheet are cleaned.
    owners = characters["group_company_owner_rights_str"].dropna()
    assert not owners.str.contains("\n|\xa0").any()

    selected = subcategories[subcategories["id_selected_int"] == 1]
    assert len(selected) > 0
    assert selected["cod_subcat_str"].str.match(r"^M[A-Z]{2}\d+$").all()
    assert not selected["cod_subcat_str"].duplicated().any()
