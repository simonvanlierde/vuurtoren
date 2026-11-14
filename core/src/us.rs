//! US federal kernels; filing-status selection stays in the sourced Python config.
use crate::{parameter, same_runs};
use pyo3::prelude::*;

type CreditResult = (Vec<f64>, Vec<Vec<f64>>);
type Pair = (Vec<f64>, Vec<f64>);

fn filing(cfg: &Bound<'_, PyAny>, field: &str, status: &str) -> PyResult<f64> {
    cfg.call_method1("by_filing_status", (field, status))?
        .extract()
}

fn ladder(cfg: &Bound<'_, PyAny>, status: &str) -> PyResult<Vec<(f64, f64)>> {
    (1..=7)
        .map(|n| {
            let upper = if n == 7 {
                f64::INFINITY
            } else {
                filing(cfg, &format!("ordinary_bracket_{n}_to"), status)?
            };
            Ok((upper, parameter(cfg, &format!("ordinary_rate_{n}"))?))
        })
        .collect()
}

fn slice(bands: &[(f64, f64)], start: f64, end: f64) -> f64 {
    let mut tax = 0.0;
    let mut lower = 0.0;
    for &(upper, rate) in bands {
        tax += (end.max(lower).min(upper) - start.max(lower).min(upper)) * rate;
        lower = upper;
    }
    tax
}

#[pyfunction]
fn us_bracket_tax(income: Vec<f64>, status: &str, cfg: &Bound<'_, PyAny>) -> PyResult<Vec<f64>> {
    same_runs(&[&income])?;
    let bands = ladder(cfg, status)?;
    Ok(income
        .into_iter()
        .map(|x| slice(&bands, 0.0, x.max(0.0)))
        .collect())
}

#[pyfunction]
fn us_ordinary_tax(
    taxable: Vec<f64>,
    excluded: Vec<f64>,
    status: &str,
    cfg: &Bound<'_, PyAny>,
) -> PyResult<Vec<f64>> {
    same_runs(&[&taxable, &excluded])?;
    let bands = ladder(cfg, status)?;
    Ok(taxable
        .iter()
        .zip(&excluded)
        .map(|(&taxable, &excluded)| {
            slice(&bands, 0.0, (taxable + excluded).max(0.0))
                - slice(&bands, 0.0, excluded.max(0.0))
        })
        .collect())
}

#[pyfunction]
fn us_excluded_earned_income(earned: Vec<f64>, cfg: &Bound<'_, PyAny>) -> PyResult<Vec<f64>> {
    same_runs(&[&earned])?;
    let limit = parameter(cfg, "feie_limit")?;
    Ok(earned.into_iter().map(|x| x.clamp(0.0, limit)).collect())
}

#[pyfunction]
fn us_taxable_income(
    earned: Vec<f64>,
    other: Vec<f64>,
    status: &str,
    cfg: &Bound<'_, PyAny>,
) -> PyResult<Vec<f64>> {
    same_runs(&[&earned, &other])?;
    let limit = parameter(cfg, "feie_limit")?;
    let deduction = filing(cfg, "standard_deduction", status)?;
    Ok(earned
        .iter()
        .zip(&other)
        .map(|(&earned, &other)| (earned + other - earned.clamp(0.0, limit) - deduction).max(0.0))
        .collect())
}

#[pyfunction]
fn us_unused_deduction(
    earned: Vec<f64>,
    other: Vec<f64>,
    status: &str,
    cfg: &Bound<'_, PyAny>,
) -> PyResult<Vec<f64>> {
    same_runs(&[&earned, &other])?;
    let limit = parameter(cfg, "feie_limit")?;
    let deduction = filing(cfg, "standard_deduction", status)?;
    Ok(earned
        .iter()
        .zip(&other)
        .map(|(&earned, &other)| {
            (deduction - (earned + other - earned.clamp(0.0, limit)).max(0.0)).max(0.0)
        })
        .collect())
}

#[pyfunction]
fn us_preferential_tax(
    gain: Vec<f64>,
    ordinary: Vec<f64>,
    status: &str,
    cfg: &Bound<'_, PyAny>,
) -> PyResult<Vec<f64>> {
    same_runs(&[&gain, &ordinary])?;
    let bands = [
        (
            filing(cfg, "ltcg_zero_rate_top", status)?,
            parameter(cfg, "ltcg_rate_1")?,
        ),
        (
            filing(cfg, "ltcg_fifteen_rate_top", status)?,
            parameter(cfg, "ltcg_rate_2")?,
        ),
        (f64::INFINITY, parameter(cfg, "ltcg_rate_3")?),
    ];
    Ok(gain
        .iter()
        .zip(&ordinary)
        .map(|(&gain, &ordinary)| {
            let start = ordinary.max(0.0);
            slice(&bands, start, start + gain.max(0.0))
        })
        .collect())
}

#[pyfunction]
fn us_niit(
    income: Vec<f64>,
    agi: Vec<f64>,
    status: &str,
    cfg: &Bound<'_, PyAny>,
) -> PyResult<Vec<f64>> {
    same_runs(&[&income, &agi])?;
    let threshold = filing(cfg, "niit_threshold", status)?;
    let rate = parameter(cfg, "niit_rate")?;
    Ok(income
        .iter()
        .zip(&agi)
        .map(|(&income, &agi)| income.max(0.0).min((agi - threshold).max(0.0)) * rate)
        .collect())
}

fn limitation(tax: f64, foreign: f64, total: f64) -> f64 {
    let share = if total > 0.0 {
        foreign.max(0.0) / total
    } else {
        0.0
    };
    tax.max(0.0) * share.clamp(0.0, 1.0)
}

#[pyfunction]
fn us_credit_limitation(tax: Vec<f64>, foreign: Vec<f64>, total: Vec<f64>) -> PyResult<Vec<f64>> {
    same_runs(&[&tax, &foreign, &total])?;
    Ok(tax
        .iter()
        .zip(&foreign)
        .zip(&total)
        .map(|((&tax, &foreign), &total)| limitation(tax, foreign, total))
        .collect())
}

#[pyfunction]
fn us_apply_credit(
    tax: Vec<f64>,
    paid: Vec<f64>,
    foreign: Vec<f64>,
    total: Vec<f64>,
    carry: Vec<Vec<f64>>,
) -> PyResult<CreditResult> {
    same_runs(&[&tax, &paid, &foreign, &total])?;
    for vintage in &carry {
        same_runs(&[&tax, vintage])?;
    }
    let mut bank = carry;
    bank.push(vec![0.0; tax.len()]);
    let mut after = Vec::with_capacity(tax.len());
    for (i, &tax) in tax.iter().enumerate() {
        let mut remaining = limitation(tax, foreign[i], total[i]);
        let paid = paid[i].max(0.0);
        let from_year = paid.min(remaining);
        remaining -= from_year;
        let mut credited = from_year;
        let vintages = bank.len() - 1;
        for vintage in &mut bank[..vintages] {
            let drawn = vintage[i].min(remaining);
            remaining -= drawn;
            credited += drawn;
            vintage[i] -= drawn;
        }
        bank[vintages][i] = paid - from_year;
        after.push(tax - credited);
    }
    if bank.len() > 10 {
        bank.drain(..bank.len() - 10);
    }
    Ok((after, bank))
}

#[pyfunction]
fn us_pfic_inclusion(growth: Vec<f64>, pool: Vec<f64>) -> PyResult<Pair> {
    same_runs(&[&growth, &pool])?;
    let inclusion: Vec<f64> = growth
        .iter()
        .zip(&pool)
        .map(|(&growth, &pool)| growth.max(0.0) - (-growth).max(0.0).min(pool))
        .collect();
    let after = pool
        .iter()
        .zip(&inclusion)
        .map(|(pool, inclusion)| pool + inclusion)
        .collect();
    Ok((inclusion, after))
}

#[pyfunction]
fn us_pfic_sale_gain(gain: Vec<f64>, pool: Vec<f64>) -> PyResult<Vec<f64>> {
    same_runs(&[&gain, &pool])?;
    Ok(gain
        .iter()
        .zip(&pool)
        .map(|(&gain, &pool)| (gain - pool).max(0.0))
        .collect())
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(us_bracket_tax, m)?)?;
    m.add_function(wrap_pyfunction!(us_ordinary_tax, m)?)?;
    m.add_function(wrap_pyfunction!(us_excluded_earned_income, m)?)?;
    m.add_function(wrap_pyfunction!(us_taxable_income, m)?)?;
    m.add_function(wrap_pyfunction!(us_unused_deduction, m)?)?;
    m.add_function(wrap_pyfunction!(us_preferential_tax, m)?)?;
    m.add_function(wrap_pyfunction!(us_niit, m)?)?;
    m.add_function(wrap_pyfunction!(us_credit_limitation, m)?)?;
    m.add_function(wrap_pyfunction!(us_apply_credit, m)?)?;
    m.add_function(wrap_pyfunction!(us_pfic_inclusion, m)?)?;
    m.add_function(wrap_pyfunction!(us_pfic_sale_gain, m)?)?;
    Ok(())
}
