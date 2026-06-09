import pytest
from pyhocon import ConfigFactory

def test_fallback_priority():
    c1 = ConfigFactory.parse_string("hero = batman")
    c2 = ConfigFactory.parse_string("hero = superman")

    # c1 falls back to c2 -> c1 is top precedence
    c3 = c1.with_fallback(c2)
    assert c3.get_string("hero") == "batman"

    # c2 falls back to c1 -> c2 is top precedence
    c4 = c2.with_fallback(c1)
    assert c4.get_string("hero") == "superman"

def test_from_dict_cloning():
    text = """
    foo = bar
    hero = superman
    """
    tree = ConfigFactory.parse_string(text)
    cloned = ConfigFactory.from_dict(tree)
    
    assert cloned.get_string("hero") == "superman"
    assert "foo" in cloned
