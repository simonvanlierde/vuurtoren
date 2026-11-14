//! Austrian scalar income arithmetic keeps decimal amounts through the boundary.
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rust_decimal::{Decimal, RoundingStrategy};

fn decimal(value: &str) -> PyResult<Decimal> {
    Decimal::from_str_exact(value)
        .or_else(|_| Decimal::from_scientific(value))
        .map_err(|e| PyValueError::new_err(e.to_string()))
}

fn parameter(cfg: &Bound<'_, PyAny>, name: &str) -> PyResult<Decimal> {
    let value = decimal(cfg.getattr(name)?.str()?.to_str()?)?;
    let places = if name == "sonderzahlung_share" {
        18
    } else if name.contains("rate") {
        4
    } else {
        2
    };
    if value.normalize().scale() > places {
        return Err(PyValueError::new_err(format!(
            "{name} supports at most {places} decimal places"
        )));
    }
    Ok(value)
}

fn money(value: Decimal) -> Decimal {
    value.round_dp_with_strategy(2, RoundingStrategy::MidpointAwayFromZero)
}

fn checked_amount(value: &str) -> PyResult<Decimal> {
    let message = "amount must be exact cents within one trillion";
    let value = decimal(value).map_err(|_| PyValueError::new_err(message))?;
    if value.abs() > Decimal::from(1_000_000_000_000_u64) || value != money(value) {
        return Err(PyValueError::new_err(message));
    }
    Ok(value)
}

fn social(gross: Decimal, cfg: &Bound<'_, PyAny>) -> PyResult<Decimal> {
    if gross <= Decimal::ZERO {
        return Ok(Decimal::ZERO);
    }
    Ok(money(
        gross.min(parameter(cfg, "social_insurance_ceiling")?)
            * parameter(cfg, "social_insurance_employee_rate")?,
    ))
}

fn income(base: Decimal, cfg: &Bound<'_, PyAny>) -> PyResult<Decimal> {
    let mut lower = Decimal::ZERO;
    let mut tax = Decimal::ZERO;
    for n in 1..=7 {
        if base <= lower {
            break;
        }
        let upper = if n == 7 {
            Decimal::from(1_000_000_000_000_u64)
        } else {
            parameter(cfg, &format!("income_bracket_{n}_to"))?
        };
        tax += (base.min(upper) - lower) * parameter(cfg, &format!("income_rate_{n}"))?;
        lower = upper;
    }
    Ok(tax)
}

fn special(base: Decimal, cfg: &Bound<'_, PyAny>) -> PyResult<Decimal> {
    if base <= parameter(cfg, "sonderzahlung_exempt_below")? {
        return Ok(Decimal::ZERO);
    }
    Ok(
        (base - parameter(cfg, "sonderzahlung_allowance")?).max(Decimal::ZERO)
            * parameter(cfg, "sonderzahlung_rate")?,
    )
}

#[pyfunction]
fn at_social_insurance(gross: &str, cfg: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(social(checked_amount(gross)?, cfg)?.to_string())
}

#[pyfunction]
fn at_income_tax(base: &str, cfg: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(income(checked_amount(base)?, cfg)?.to_string())
}

#[pyfunction]
fn at_sonderzahlung_tax(base: &str, cfg: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(special(checked_amount(base)?, cfg)?.to_string())
}

#[pyfunction]
fn at_gross_to_net(gross: &str, sonderzahlungen: bool, cfg: &Bound<'_, PyAny>) -> PyResult<String> {
    let gross = checked_amount(gross)?;
    if gross <= Decimal::ZERO {
        return Ok("0".into());
    }
    let sv = social(gross, cfg)?;
    let credit = parameter(cfg, "employee_credit")?;
    let tax = if sonderzahlungen {
        let share = parameter(cfg, "sonderzahlung_share")?;
        let extra = gross * share;
        let sv_extra = sv * share;
        (income(gross - extra - (sv - sv_extra), cfg)? - credit).max(Decimal::ZERO)
            + special(extra - sv_extra, cfg)?
    } else {
        (income(gross - sv, cfg)? - credit).max(Decimal::ZERO)
    };
    Ok(money(gross - sv - tax).to_string())
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(at_social_insurance, m)?)?;
    m.add_function(wrap_pyfunction!(at_income_tax, m)?)?;
    m.add_function(wrap_pyfunction!(at_sonderzahlung_tax, m)?)?;
    m.add_function(wrap_pyfunction!(at_gross_to_net, m)?)?;
    Ok(())
}
