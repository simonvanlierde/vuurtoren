//! Numeric kernels for the Python projection engine. Parameters come from its exact-decimal loader.
mod at;
mod us;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

fn parameter(cfg: &Bound<'_, PyAny>, name: &str) -> PyResult<f64> {
    cfg.getattr(name)?.extract()
}

fn same_runs(arrays: &[&[f64]]) -> PyResult<()> {
    let Some(first) = arrays.first() else {
        return Ok(());
    };
    if arrays.iter().any(|a| a.len() != first.len()) {
        return Err(PyValueError::new_err(
            "arrays must have the same number of runs",
        ));
    }
    if arrays.iter().flat_map(|a| a.iter()).any(|x| !x.is_finite()) {
        return Err(PyValueError::new_err("arrays must contain finite values"));
    }
    Ok(())
}

fn cents(value: f64) -> f64 {
    (value * 100.0).round_ties_even() / 100.0
}

#[pyfunction]
fn forfaitair_income_array(
    bank: Vec<f64>,
    investments: Vec<f64>,
    debt: Vec<f64>,
    fiscal_partners: bool,
    cfg: &Bound<'_, PyAny>,
) -> PyResult<Vec<f64>> {
    same_runs(&[&bank, &investments, &debt])?;
    let n = if fiscal_partners { 2.0 } else { 1.0 };
    let threshold = parameter(cfg, "box3_debt_threshold_per_person")? * n;
    let allowance = parameter(cfg, "box3_allowance_per_person")? * n;
    let bank_rate = parameter(cfg, "box3_forfait_bank")?;
    let investment_rate = parameter(cfg, "box3_forfait_investments")?;
    let debt_rate = parameter(cfg, "box3_forfait_debt")?;
    Ok(bank
        .iter()
        .zip(&investments)
        .zip(&debt)
        .map(|((&bank, &investments), &debt)| {
            let eligible_debt = (debt - threshold).max(0.0);
            let base = bank + investments - eligible_debt;
            if base <= allowance {
                return 0.0;
            }
            let income =
                bank * bank_rate + investments * investment_rate - eligible_debt * debt_rate;
            cents((income * ((base - allowance) / base)).max(0.0))
        })
        .collect())
}

#[pyfunction]
fn wwr_loss_carry(
    actual_return: Vec<f64>,
    loss_carry: Option<Vec<f64>>,
    fiscal_partners: bool,
    cfg: &Bound<'_, PyAny>,
) -> PyResult<Vec<f64>> {
    let loss_carry = loss_carry.unwrap_or_else(|| vec![0.0; actual_return.len()]);
    same_runs(&[&actual_return, &loss_carry])?;
    let n = if fiscal_partners { 2.0 } else { 1.0 };
    let allowance = parameter(cfg, "wwr_allowance_per_person")? * n;
    let threshold = parameter(cfg, "wwr_loss_threshold")?;
    Ok(actual_return
        .iter()
        .zip(&loss_carry)
        .map(|(&actual, &pool)| {
            let income = if actual > 0.0 {
                (actual - allowance).max(0.0)
            } else {
                actual
            };
            pool - pool.min(income.max(0.0)) + (-income - threshold).max(0.0)
        })
        .collect())
}

fn phased(maximum: f64, income: f64, start: f64, rate: f64) -> f64 {
    (maximum - rate * (income - start).max(0.0)).max(0.0)
}

#[pyfunction]
fn box1_tax_array(
    income: Vec<f64>,
    labour_income: Vec<f64>,
    aow_share: f64,
    cfg: &Bound<'_, PyAny>,
) -> PyResult<Vec<f64>> {
    same_runs(&[&income, &labour_income])?;
    if !(0.0..=1.0).contains(&aow_share) {
        return Err(PyValueError::new_err(
            "aow_share must be between zero and one",
        ));
    }
    let p = |name| parameter(cfg, name);
    let b1 = p("box1_bracket_1_to")?;
    let b2 = p("box1_bracket_2_to")?;
    let r1 = p("box1_rate_1")?;
    let r2 = p("box1_rate_2")?;
    let r3 = p("box1_rate_3")?;
    let premium = p("aow_premium_rate")?;
    let general = p("general_credit_max")?;
    let general_aow = p("general_credit_max_aow")?;
    let general_start = p("general_credit_phaseout_from")?;
    let general_rate = p("general_credit_phaseout_rate")?;
    let general_rate_aow = p("general_credit_phaseout_rate_aow")?;
    let elderly = p("elderly_credit_max")?;
    let elderly_start = p("elderly_credit_phaseout_from")?;
    let elderly_rate = p("elderly_credit_phaseout_rate")?;
    let k1 = p("labour_credit_knot_1")?;
    let k2 = p("labour_credit_knot_2")?;
    let k3 = p("labour_credit_knot_3")?;
    let l1 = p("labour_credit_rate_1")?;
    let l2 = p("labour_credit_rate_2")?;
    let l3 = p("labour_credit_rate_3")?;
    let base2 = p("labour_credit_base_2")?;
    let base3 = p("labour_credit_base_3")?;
    let labour_max = p("labour_credit_max")?;
    let labour_phaseout = p("labour_credit_phaseout_rate")?;
    Ok(income
        .iter()
        .zip(&labour_income)
        .map(|(&income, &labour)| {
            let income = income.max(0.0);
            let labour = labour.max(0.0);
            let tax = |first_rate| {
                income.min(b1) * first_rate
                    + (income - b1).max(0.0).min(b2 - b1) * r2
                    + (income - b2).max(0.0) * r3
            };
            let credit = if labour <= k1 {
                l1 * labour
            } else if labour <= k2 {
                base2 + l2 * (labour - k1)
            } else if labour <= k3 {
                base3 + l3 * (labour - k2)
            } else {
                phased(labour_max, labour, k3, labour_phaseout)
            };
            let below = tax(r1) - phased(general, income, general_start, general_rate) - credit;
            let above = tax(r1 - premium)
                - phased(general_aow, income, general_start, general_rate_aow)
                - phased(elderly, income, elderly_start, elderly_rate);
            (1.0 - aow_share) * below.max(0.0) + aow_share * above.max(0.0)
        })
        .collect())
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
#[pyo3(signature = (bank, investments, debt, actual_return, year, fiscal_partners, cfg, elect=true, loss_carry=None))]
fn box3_tax_array(
    bank: Vec<f64>,
    investments: Vec<f64>,
    debt: Vec<f64>,
    actual_return: Option<Vec<f64>>,
    year: i32,
    fiscal_partners: bool,
    cfg: &Bound<'_, PyAny>,
    elect: bool,
    loss_carry: Option<Vec<f64>>,
) -> PyResult<Vec<f64>> {
    same_runs(&[&bank, &investments, &debt])?;
    for (name, values) in [
        ("bank", &bank),
        ("investments", &investments),
        ("debt", &debt),
    ] {
        if values.iter().any(|v| *v < 0.0) {
            return Err(PyValueError::new_err(format!(
                "{name} must not be negative"
            )));
        }
    }
    if let Some(actual) = actual_return.as_ref() {
        same_runs(&[&bank, actual])?;
    }
    let switch: i32 = cfg.getattr("regime_switch_year")?.extract()?;
    if year >= switch {
        let actual = actual_return
            .ok_or_else(|| PyValueError::new_err("regime B requires actual_return"))?;
        let pool = loss_carry.unwrap_or_else(|| vec![0.0; bank.len()]);
        same_runs(&[&actual, &pool])?;
        let n = if fiscal_partners { 2.0 } else { 1.0 };
        let allowance = parameter(cfg, "wwr_allowance_per_person")? * n;
        let rate = parameter(cfg, "wwr_rate")?;
        return Ok(actual
            .iter()
            .zip(&pool)
            .map(|(&actual, &pool)| {
                let income = if actual > 0.0 {
                    (actual - allowance).max(0.0)
                } else {
                    actual
                };
                let taxable = income.max(0.0) - pool.min(income.max(0.0));
                cents(taxable * rate)
            })
            .collect());
    }
    let mut income = forfaitair_income_array(bank, investments, debt, fiscal_partners, cfg)?;
    if elect && let Some(actual) = actual_return {
        for (income, actual) in income.iter_mut().zip(actual) {
            *income = income.min(actual.max(0.0));
        }
    }
    let rate = parameter(cfg, "box3_rate")?;
    Ok(income
        .into_iter()
        .map(|income| cents(income * rate))
        .collect())
}

#[pymodule]
fn vuurtoren_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(forfaitair_income_array, m)?)?;
    m.add_function(wrap_pyfunction!(box1_tax_array, m)?)?;
    m.add_function(wrap_pyfunction!(box3_tax_array, m)?)?;
    m.add_function(wrap_pyfunction!(wwr_loss_carry, m)?)?;
    us::register(m)?;
    at::register(m)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::cents;

    #[test]
    fn cent_rounding_uses_even_ties() {
        for (value, expected) in [(2.675, 2.68), (2.685, 2.68), (-2.675, -2.68)] {
            assert!((cents(value) - expected).abs() < 1e-12);
        }
    }
}
