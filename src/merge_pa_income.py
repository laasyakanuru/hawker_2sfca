'''
Merge Planning Area accessibility data with household income shares.

Inputs : agg_access_planning_area.csv
         fact_pa_household_income.csv
Outputs: agg_access_planning_area_with_income.csv
         planning_area_clustering_input.csv

Join logic:
  1. Standardise pa_key in both datasets.
  2. Aggregate household counts by Planning Area.
  3. Calculate low- and high-income household percentages.
  4. Left join income percentages to accessibility data using pa_key.
  5. Filter to one row per Planning Area for clustering.

Income definitions (provisional analytical thresholds):
  Low income  : monthly household income from work below SGD 3,000.
  High income : monthly household income from work of SGD 20_000 or more.
  Denominator : all households in each Planning Area.
  NoEmployedPerson is included in the denominator but is not classified
  as either low or high income.

Notes:
  Income refers to household income from work, not individual salary.
  Percentages range from 0 to 100.
  Missing income data remains missing; it is not replaced with zero.
  Low- and high-income percentages do not sum to 100 because other
  household categories are included in the denominator.

Clustering extract:
  dwelling_type = ALL
  scenario      = baseline
  method        = 2sfcas
  catchment_m   = 1000
'''
#%%
from pathlib import Path

import pandas as pd

import config


# Folder containing the input CSV files.
DATA_DIR = config.PROCESSED

LOW_INCOME_BANDS = [
    'Below_1_000',
    '1_000_1_999',
    '2_000_2_999',
]

HIGH_INCOME_BANDS = [
    # '10_000_10_999',
    # '11_000_11_999',
    # '12_000_12_999',
    # '13_000_13_999',
    # '14_000_14_999',
    # '15_000_17_499',
    # '17_500_19_999',
    '20_000andOver',
]


def main():
    # 1. Load the input datasets.
    access = pd.read_csv(
        DATA_DIR / 'agg_access_planning_area.csv'
    )
    income = pd.read_csv(
        DATA_DIR / 'fact_pa_household_income.csv'
    )

    # 2. Standardise and validate the join key.
    for df in (access, income):
        df['pa_key'] = df['pa_key'].str.strip().str.upper()

        if df['pa_key'].isna().any() or df['pa_key'].eq('').any():
            raise ValueError('Missing or empty pa_key values found.')

    # 3. Validate household counts and income-band uniqueness.
    income['households'] = pd.to_numeric(
        income['households'], errors='raise'
    )

    if (
        income['households'].isna().any()
        or (income['households'] < 0).any()
    ):
        raise ValueError('Household counts contain missing or negative values.')

    if income.duplicated(['pa_key', 'income_band']).any():
        raise ValueError('Duplicate Planning Area and income-band pairs found.')

    # 4. Identify low- and high-income household counts.
    income['low_households'] = income['households'].where(
        income['income_band'].isin(LOW_INCOME_BANDS), 0
    )
    income['high_households'] = income['households'].where(
        income['income_band'].isin(HIGH_INCOME_BANDS), 0
    )

    # 5. Aggregate household counts by Planning Area.
    summary = income.groupby('pa_key', as_index=False).agg(
        total_households=('households', 'sum'),
        low_households=('low_households', 'sum'),
        high_households=('high_households', 'sum'),
    )

    # Keep percentages missing when the denominator is zero.
    denominator = summary['total_households'].where(
        summary['total_households'] > 0
    )

    summary['pct_low_income_households'] = (
        summary['low_households'] / denominator * 100
    )
    summary['pct_high_income_households'] = (
        summary['high_households'] / denominator * 100
    )

    # 6. Add the two income percentages, preserving all access rows.
    result = access.merge(
        summary[
            [
                'pa_key',
                'pct_low_income_households',
                'pct_high_income_households',
            ]
        ],
        on='pa_key',
        how='left',
        validate='many_to_one',
        indicator=True,
    )

    unmatched = result.loc[
        result['_merge'] == 'left_only', 'pa_key'
    ].unique()

    print('Planning Areas without income data:', unmatched.tolist())

    result = result.drop(columns='_merge')

    merged_path = DATA_DIR / 'agg_access_planning_area_with_income.csv'
    result.to_csv(merged_path, index=False, encoding='utf-8-sig')

    # # 7. Create a one-row-per-Planning-Area extract for clustering.
    # clustering_data = result.loc[
    #     (result['dwelling_type'] == 'ALL')
    #     & (result['scenario'] == 'baseline')
    #     & (result['method'] == 'e2sfca_gauss')
    #     & (result['catchment_m'] == 1000)
    # ].copy()

    # if clustering_data.empty:
    #     raise ValueError('No rows match the selected clustering conditions.')

    # if not clustering_data['pa_key'].is_unique:
    #     raise ValueError('The clustering extract contains duplicate Planning Areas.')

    # clustering_path = DATA_DIR / 'planning_area_clustering_input.csv'
    # clustering_data.to_csv(
    #     clustering_path, index=False, encoding='utf-8-sig'
    # )

    # print(f'Saved: {merged_path} ({len(result):,} rows)')
    # print(f'Saved: {clustering_path} ({len(clustering_data):,} rows)')


if __name__ == '__main__':
    main()
# %%
