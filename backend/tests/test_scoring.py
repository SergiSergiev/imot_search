from types import SimpleNamespace

from app.services.ai import parse_with_rules
from app.services.scoring import score_listing
from app.services.importer import _listing_links, _pagination_links, _tls_verify_for_imot_url, parse_listing_page


def listing(**overrides):
    defaults = dict(
        district="Лозенец", price_eur=230000, property_type="апартамент", room_count=3,
        area_sqm=96, price_per_sqm_eur=2395, floor_number=3, total_floors=6,
        floor_label=None, condition="обзаведен", description="Подробно описание " * 40,
        features=[SimpleNamespace(key="elevator", normalized_value=True)],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_bulgarian_query_parser():
    intent = parse_with_rules("Търся тристаен в Лозенец до 250 000 евро, поне 90 кв.м, не последен етаж")
    assert intent.max_price_eur == 250000
    assert intent.min_area_sqm == 90
    assert intent.room_counts == [3]
    assert intent.locations == ["Лозенец"]
    assert intent.exclude_last_floor is True


def test_good_match_scores_high():
    intent = parse_with_rules("Търся тристаен в Лозенец до 250 000 евро, поне 90 кв.м, с асансьор")
    score, passed, explanations = score_listing(listing(), intent, 2500)
    assert passed is True
    assert score >= 80
    assert any(item.criterion == "location" and item.status == "met" for item in explanations)


def test_hard_failure_caps_score():
    intent = parse_with_rules("Търся тристаен в Лозенец до 200 000 евро, не последен етаж")
    score, passed, _ = score_listing(listing(price_eur=260000, floor_number=6, total_floors=6), intent, 2500)
    assert passed is False
    assert score <= 39


def test_agency_pagination_and_listing_links_are_separate():
    html = """
      <a href="/obiava-1b179196513954298-prodava-dvustaen">Имот</a>
      <a href="https://adress.imot.bg/obiavi/p-2">2</a>
      <a href="https://adress.imot.bg/obiavi/p-11?x=1">11</a>
      <a href="https://other.imot.bg/obiavi/p-3">друга агенция</a>
    """
    assert _listing_links("https://adress.imot.bg/", html) == ["https://adress.imot.bg/obiava-1b179196513954298-prodava-dvustaen"]
    assert _pagination_links("https://adress.imot.bg/", html) == [
        "https://adress.imot.bg/obiavi/p-2",
        "https://adress.imot.bg/obiavi/p-11",
    ]


def test_imot_slug_is_stable_source_id():
    item = parse_listing_page(
        "https://adress.imot.bg/obiava-1b179196513954298-prodava-dvustaen-apartament-grad-varna",
        "<html><h1>Двустаен апартамент</h1><p>град Варна, 70 кв. м, 150000 EUR</p></html>",
    )
    assert item.source_listing_id == "1b179196513954298"
    assert item.city == "Варна"


def test_tls_hostname_relaxation_is_narrowly_scoped():
    assert _tls_verify_for_imot_url("https://adress.imot.bg/") is True
    context = _tls_verify_for_imot_url("https://address_vt.imot.bg/")
    assert context is not True
    assert context.check_hostname is False
    assert context.verify_mode.name == "CERT_REQUIRED"


def test_current_imot_detail_structure_is_parsed():
    html = """
      <div class="advHeader"><div class="title">Продава 3-СТАЕН</div>
      <div class="location">град Велико Търново, Колю Фичето</div></div>
      <div class="adPrice"><div class="cena">175 000 €</div></div>
      <div class="adParams"><div>Площ:<strong>95 m<sup>2</sup></strong></div>
      <div>Етаж:<strong>4-ти от 7</strong></div></div>
      <div class="moreInfo"><div class="text">Светъл апартамент с асансьор.</div></div>
      <img data-src="https://cdn.example/image.jpg">
    """
    item = parse_listing_page("https://address_vt.imot.bg/obiava-1c123456-prodava", html)
    assert item.title == "Продава 3-СТАЕН"
    assert item.city == "Велико Търново"
    assert item.district == "Колю Фичето"
    assert item.price_eur == 175000
    assert item.area_sqm == 95
    assert item.floor_number == 4
    assert item.total_floors == 7
    assert item.room_count == 3
    assert item.description == "Светъл апартамент с асансьор."
