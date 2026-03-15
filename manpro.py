import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy_financial as npf
from PIL import Image

# ==========================================
# 1. PAGE CONFIGURATION & HEADER
# ==========================================
logo_path = "assets/PSchi.png"
try:
    logo = Image.open(logo_path)
    st.set_page_config(layout="wide", page_title="PSChi Dashboard", page_icon=logo)
except FileNotFoundError:
    st.set_page_config(layout="wide", page_title="PSChi Dashboard", page_icon="🛢️")
    logo = None

col_logo, col_title = st.columns([1, 10])
with col_logo:
    if logo:
        st.image(logo, use_container_width=True)
with col_title:
    st.title("PSChi: Enterprise PSC Economic Simulator")
    
st.markdown("""
Selamat datang di **PSChi**. Platform simulasi keekonomian *Production Sharing Contract* (PSC) Cost Recovery. 
Sesuaikan parameter di panel samping dan jelajahi analisis mendalam melalui visualisasi interaktif di bawah ini.
""")
st.markdown("---")

# ==========================================
# 2. SIDEBAR INPUTS
# ==========================================
st.sidebar.markdown("### ⚙️ PSChi Control Panel")

with st.sidebar.expander("📈 Production Profile", expanded=True):
    q_initial = st.number_input("Initial Rate (BOPD)", value=30000, step=1000)
    q_peak = st.number_input("Peak Rate (BOPD)", value=50000, step=1000)
    plateau_years = st.number_input("Plateau Duration (Years)", value=3, step=1)
    decline_rate = st.number_input("Decline Rate (%)", value=10.0, step=1.0) / 100
    prod_years = st.number_input("Production Duration (Years)", value=20, step=1)

with st.sidebar.expander("🏗️ CAPEX (Exploration & Dev)", expanded=False):
    exp_years = st.number_input("Exploration Duration (Years)", value=6, step=1)
    exp_costs_input = st.text_input("Exploration Cost/Year (MUS$)", value="15000, 15000, 100000, 75000, 50000, 20000")
    
    dev_years = st.number_input("Development Duration (Years)", value=3, step=1)
    dev_costs_input = st.text_input("Development Cost/Year (MUS$)", value="300000, 500000, 400000")
    
    tangible_pct = st.number_input("Tangible Split (%)", value=75.0, step=1.0) / 100
    intangible_pct = 1.0 - tangible_pct

with st.sidebar.expander("💰 Economic & PSC Terms", expanded=False):
    oil_price = st.number_input("Oil Price ($/bbl)", value=55.0, step=1.0)
    opex_per_bbl = st.number_input("Opex ($/bbl)", value=10.0, step=1.0)
    
    ftp_rate = st.number_input("FTP (%)", value=20.0, step=1.0) / 100
    tax_rate = st.number_input("Corporate Tax (%)", value=44.0, step=1.0) / 100
    gov_split_after_tax = st.number_input("Gov After-Tax Split (%)", value=85.0, step=1.0) / 100
    dmo_fee_rate = st.number_input("DMO Fee (%)", value=25.0, step=1.0) / 100
    discount_rate = st.number_input("Discount Rate for NPV (%)", value=10.0, step=1.0) / 100
    
    ctr_split_after_tax = 1 - gov_split_after_tax
    ctr_split_before_tax = ctr_split_after_tax / (1 - tax_rate)
    gov_split_before_tax = 1 - ctr_split_before_tax

with st.sidebar.expander("📉 Depreciation Rules", expanded=False):
    dep_group = st.selectbox("Tangible Depreciation Group", ["Group 1 (50%)", "Group 2 (25%)", "Group 3 (12.5%)"], index=1)
    dep_years = st.number_input("Target Depreciation (Years)", value=5, min_value=1, step=1)


# ==========================================
# 3. CORE CALCULATION FUNCTION 
# ==========================================
def run_psc_model(override_oil_price=None):
    current_oil_price = override_oil_price if override_oil_price is not None else oil_price
    
    try:
        exploration_costs_list = [float(x.strip()) for x in exp_costs_input.split(',')]
    except ValueError:
        exploration_costs_list = [0]
        
    try:
        development_costs_list = [float(x.strip()) for x in dev_costs_input.split(',')]
    except ValueError:
        development_costs_list = [0]

    exploration_costs_list = (exploration_costs_list + [0]*exp_years)[:exp_years]
    development_costs_list = (development_costs_list + [0]*dev_years)[:dev_years]

    actual_prod_years = prod_years + 1
    prod_start_year = exp_years + dev_years
    total_years = prod_start_year + actual_prod_years
    years_array = np.arange(1, total_years + 1)
    
    exp_costs = np.zeros(total_years)
    exp_costs[0:exp_years] = exploration_costs_list
    
    dev_costs = np.zeros(total_years)
    dev_costs[exp_years:prod_start_year] = development_costs_list
    
    dev_tangible = dev_costs * tangible_pct
    dev_intangible = dev_costs * intangible_pct

    prod_bopd = np.zeros(total_years)
    if actual_prod_years > 0:
        prod_bopd[prod_start_year] = q_initial
        for i in range(1, min(plateau_years + 1, actual_prod_years)):
            if prod_start_year + i < total_years:
                prod_bopd[prod_start_year + i] = q_peak
        for i in range(plateau_years + 1, actual_prod_years):
            if prod_start_year + i < total_years:
                prod_bopd[prod_start_year + i] = prod_bopd[prod_start_year + i - 1] * (1 - decline_rate)

    prod_mstb = (prod_bopd * 365) / 1000

    rate_map = {"Group 1 (50%)": 0.50, "Group 2 (25%)": 0.25, "Group 3 (12.5%)": 0.125}
    depreciation_rate = rate_map[dep_group]
    
    depreciation_schedule_pct = []
    balance = 1.0
    for i in range(dep_years):
        if i == dep_years - 1:
            depreciation_schedule_pct.append(balance)
        else:
            charge = balance * depreciation_rate
            depreciation_schedule_pct.append(charge)
            balance -= charge

    total_tangible_pool = np.sum(dev_tangible)
    depreciation = np.zeros(total_years)
    
    for i in range(len(depreciation_schedule_pct)):
        target_year = prod_start_year + i
        if target_year < total_years:
            depreciation[target_year] = total_tangible_pool * depreciation_schedule_pct[i]

    finding_amort = np.zeros(total_years)
    intangible_amort = np.zeros(total_years)
    if prod_start_year < total_years:
        finding_amort[prod_start_year] = np.sum(exp_costs)
        intangible_amort[prod_start_year] = np.sum(dev_intangible)

    gross_revenue = prod_mstb * current_oil_price
    opex = prod_mstb * opex_per_bbl
    
    ftp = gross_revenue * ftp_rate
    gov_ftp = ftp * gov_split_before_tax
    ctr_ftp = ftp * ctr_split_before_tax
    
    gr_minus_ftp = gross_revenue - ftp
    total_costs_amort = finding_amort + intangible_amort + depreciation + opex

    recovered = np.zeros(total_years)
    unrecovered = np.zeros(total_years)
    ets = np.zeros(total_years)
    current_unrecovered_pool = 0

    for i in range(total_years):
        if prod_mstb[i] > 0:
            pool_to_recover = current_unrecovered_pool + total_costs_amort[i]
            recovered[i] = min(gr_minus_ftp[i], pool_to_recover)
            
            current_unrecovered_pool = pool_to_recover - recovered[i]
            unrecovered[i] = current_unrecovered_pool
            
            ets[i] = gr_minus_ftp[i] - recovered[i]

    gov_equity = ets * gov_split_before_tax
    ctr_equity = ets * ctr_split_before_tax

    dmo_gross = np.where(prod_mstb > 0, gross_revenue * ctr_split_before_tax * 0.25, 0)
    if prod_start_year < total_years:
        dmo_gross[prod_start_year] = 0  
        
    dmo_fee = dmo_gross * dmo_fee_rate
    dmo_penalty = dmo_gross - dmo_fee

    net_ctr_share = np.where(prod_mstb > 0, ctr_ftp + ctr_equity - dmo_penalty, 0)
    taxable_income = np.maximum(0, net_ctr_share)
    tax_paid = taxable_income * tax_rate

    cash_in = np.where(prod_mstb > 0, recovered + net_ctr_share, 0)
    cash_out = np.where(prod_mstb > 0, opex + tax_paid, exp_costs + dev_tangible + dev_intangible)
    
    net_cf = np.where(prod_mstb > 0, cash_in - cash_out, -cash_out)
    gov_take = gov_ftp + gov_equity + dmo_penalty + tax_paid
    
    return {
        'years': years_array,
        'prod_bopd': prod_bopd,
        'prod_mstb': prod_mstb,
        'gross_revenue': gross_revenue,
        'recovered': recovered,
        'unrecovered': unrecovered,
        'net_cf': net_cf,
        'gov_take': gov_take,
        'tax_paid': tax_paid,
        'total_costs_amort': total_costs_amort,
        'cash_in': cash_in,
        'cash_out': cash_out,
        'exp_costs': exp_costs,
        'dev_tangible': dev_tangible,
        'dev_intangible': dev_intangible,
        'ftp': ftp,
        'gov_ftp': gov_ftp,
        'ctr_ftp': ctr_ftp,
        'gov_equity': gov_equity,
        'ctr_equity': ctr_equity,
        'dmo_penalty': dmo_penalty,
        'finding_amort': finding_amort,
        'depreciation': depreciation,
        'intangible_amort': intangible_amort,
        'opex': opex,
        'gr_minus_ftp': gr_minus_ftp,
        'ets': ets,
        'net_ctr_share': net_ctr_share,
        'dmo_gross': dmo_gross,
        'dmo_fee': dmo_fee,
        'prod_start_year': prod_start_year
    }

results = run_psc_model()

# ==========================================
# 4. AGREGASI & INDIKATOR UTAMA
# ==========================================
total_gross_revenue = np.sum(results['gross_revenue'])
total_gov_take = np.sum(results['gov_take'])
gov_take_pct = total_gov_take / total_gross_revenue if total_gross_revenue > 0 else 0

total_contractor_take_after_tax = np.sum(results['net_ctr_share']) - np.sum(results['tax_paid'])

npv_base = npf.npv(discount_rate, results['net_cf']) / (1 + discount_rate)
try:
    irr_base = npf.irr(results['net_cf'])
except Exception:
    irr_base = 0

cumulative_cf = np.cumsum(results['net_cf'])
payback_year = "-"
for y, val in enumerate(cumulative_cf):
    if val >= 0 and y >= results['prod_start_year']:
        payback_year = f"Year {y+1}"
        break

# ==========================================
# 5. TABBED USER INTERFACE
# ==========================================
# MENAMBAHKAN TAB "ABOUT"
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard & Charts", "📑 Economic Tables", "📈 Sensitivity Analysis", "ℹ️ About PSChi"])

# ------------------------------------------
# TAB 1: DASHBOARD
# ------------------------------------------
with tab1:
    st.markdown("### 🏆 Key Economic Indicators")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Reserve (MMBO)", f"{np.sum(results['prod_mstb'])/1000:.2f}")
    col2.metric(f"NPV @{discount_rate*100:.0f}% (MUS$)", f"{npv_base:,.0f}")
    col3.metric("IRR Full Cycle", f"{irr_base:.2%}")
    col4.metric("Gov Take (%)", f"{gov_take_pct:.2%}")
    col5.metric("Payback Period", payback_year)
    st.markdown("---")

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        fig_prod = make_subplots(specs=[[{"secondary_y": True}]])
        fig_prod.add_trace(go.Bar(x=results['years'], y=results['prod_bopd'], name="BOPD", marker_color='teal'), secondary_y=False)
        fig_prod.add_trace(go.Scatter(x=results['years'], y=np.cumsum(results['prod_mstb']), name="Cum. Prod (MSTB)", line=dict(color='orange', width=3)), secondary_y=True)
        fig_prod.update_layout(title="📈 Production Profile & Cumulative", xaxis_title="Year", template='plotly_white')
        fig_prod.update_yaxes(title_text="BOPD", secondary_y=False)
        fig_prod.update_yaxes(title_text="MSTB (Cumulative)", secondary_y=True)
        st.plotly_chart(fig_prod, use_container_width=True)

    with col_c2:
        fig_cf = go.Figure()
        fig_cf.add_trace(go.Bar(x=results['years'], y=results['net_cf'], name="Yearly CF", marker_color=np.where(results['net_cf']<0, 'crimson', 'forestgreen')))
        fig_cf.add_trace(go.Scatter(x=results['years'], y=cumulative_cf, name="Cumulative CF", line=dict(color='gold', width=3)))
        fig_cf.update_layout(title="💵 Contractor Net Cash Flow", xaxis_title="Year", yaxis_title="MUS$", template='plotly_white')
        st.plotly_chart(fig_cf, use_container_width=True)

    st.markdown("---")
    
    col_c3, col_c4 = st.columns(2)
    with col_c3:
        st.markdown("### 🌊 PSC Distribution Waterfall")
        fig_waterfall = go.Figure(go.Waterfall(
            name="PSC Split", orientation="v",
            measure=["relative", "relative", "relative", "relative", "relative", "relative", "total"],
            x=["Gross Revenue", "Cost Recovery", "Gov FTP", "Gov Equity", "DMO Penalty", "Corporate Tax", "Contractor Take"],
            textposition="outside",
            text=[
                f"{total_gross_revenue:,.0f}", 
                f"-{np.sum(results['recovered']):,.0f}", 
                f"-{np.sum(results['gov_ftp']):,.0f}", 
                f"-{np.sum(results['gov_equity']):,.0f}", 
                f"-{np.sum(results['dmo_penalty']):,.0f}", 
                f"-{np.sum(results['tax_paid']):,.0f}", 
                f"{total_contractor_take_after_tax:,.0f}"
            ],
            y=[
                total_gross_revenue, 
                -np.sum(results['recovered']), 
                -np.sum(results['gov_ftp']), 
                -np.sum(results['gov_equity']), 
                -np.sum(results['dmo_penalty']), 
                -np.sum(results['tax_paid']), 
                total_contractor_take_after_tax
            ],
            decreasing={"marker":{"color":"crimson"}},
            increasing={"marker":{"color":"teal"}},
            totals={"marker":{"color":"forestgreen"}}
        ))
        fig_waterfall.update_layout(title="Distribusi Pendapatan (Gross Rev. ke Ctr Net Take)", template='plotly_white')
        st.plotly_chart(fig_waterfall, use_container_width=True)
        
    with col_c4:
        st.markdown("### 🥧 Gross Revenue Allocation")
        labels = ['Cost Recovery', 'Government Take', 'Contractor Take (After Tax)']
        values = [np.sum(results['recovered']), total_gov_take, total_contractor_take_after_tax] 
        
        fig_pie = go.Figure(data=[go.Pie(
            labels=labels, 
            values=values, 
            hole=.4, 
            marker_colors=['#4C72B0', '#55A868', '#C44E52'],
            textinfo='label+percent',
            insidetextorientation='radial'
        )])
        fig_pie.update_layout(title="Proporsi Pembagian Total Pendapatan", template='plotly_white')
        st.plotly_chart(fig_pie, use_container_width=True)


# ------------------------------------------
# TAB 2: DATA & TABLES
# ------------------------------------------
with tab2:
    st.subheader("📋 Executive Summary")
    
    cf_point_forward = results['net_cf'][exp_years:]
    try:
        irr_point_forward = npf.irr(cf_point_forward)
    except Exception:
        irr_point_forward = 0
        
    npv_point_forward = npf.npv(discount_rate, cf_point_forward) / (1 + discount_rate)

    summary_data = [
        ["1", "Produksi Gas", "BSCF", "-"],
        ["2", "Produksi Minyak", "MSTB", f"{np.sum(results['prod_mstb']):,.2f}"],
        ["3", "Harga Gas", "US$/MMBTU", "-"],
        ["4", "Harga Minyak", "US$/bbl", f"{oil_price:,.2f}"],
        ["5", "Gross Revenue", "MUS$", f"{total_gross_revenue:,.2f}"],
        ["6", "FTP:", "MUS$", f"{np.sum(results['ftp']):,.2f}"],
        ["", "    Gov FTP", "MUS$", f"{np.sum(results['gov_ftp']):,.2f}"],
        ["", "    Contr FTP", "MUS$", f"{np.sum(results['ctr_ftp']):,.2f}"],
        ["7", "Sunk Cost", "MUS$", f"{np.sum(results['exp_costs']):,.2f}"],
        ["8", "Investment (CAPEX)", "MUS$", f"{np.sum(results['dev_tangible']) + np.sum(results['dev_intangible']):,.2f}"],
        ["", "    Tangible", "MUS$", f"{np.sum(results['dev_tangible']):,.2f}"],
        ["", "    Intangible", "MUS$", f"{np.sum(results['dev_intangible']):,.2f}"],
        ["9", "Opex", "MUS$", f"{np.sum(results['opex']):,.2f}"],
        ["10", "Cost Recovery", "MUS$", f"{np.sum(results['recovered']):,.2f}"],
        ["", "    (% Gross Rev.)", "%", f"{np.sum(results['recovered'])/total_gross_revenue:.2%}" if total_gross_revenue > 0 else "0%"],
        ["11", "ETS (Equity to be Split)", "MUS$", f"{np.sum(results['ets']):,.2f}"],
        ["", "    Contr Equity Share", "MUS$", f"{np.sum(results['ctr_equity']):,.2f}"],
        ["", "    Gov Equity Share", "MUS$", f"{np.sum(results['gov_equity']):,.2f}"],
        ["12", "Contractor Profitability", "", ""],
        ["", "    Contractor Net Cash Flow", "MUS$", f"{np.sum(results['net_cf']):,.2f}"],
        ["", "    % Contractor Share", "%", f"{np.sum(results['net_cf'])/total_gross_revenue:.2%}" if total_gross_revenue > 0 else "0%"],
        ["", "    IRR Point Forward", "%", f"{irr_point_forward:.2%}" if not pd.isna(irr_point_forward) else "-"],
        ["", f"    NPV Point Forward @{discount_rate*100:.0f}%", "MUS$", f"{npv_point_forward:,.2f}"],
        ["", "    IRR Full Cycle", "%", f"{irr_base:.2%}" if not pd.isna(irr_base) else "-"],
        ["13", "Gov Profitability", "", ""],
        ["", "    Gov FTP", "MUS$", f"{np.sum(results['gov_ftp']):,.2f}"],
        ["", "    Gov Equity Share", "MUS$", f"{np.sum(results['gov_equity']):,.2f}"],
        ["", "    Net DMO", "MUS$", f"{np.sum(results['dmo_penalty']):,.2f}"],
        ["", "    Tax", "MUS$", f"{np.sum(results['tax_paid']):,.2f}"],
        ["", "    Gov Take", "MUS$", f"{total_gov_take:,.2f}"],
        ["", "    % Gov Take", "%", f"{gov_take_pct:.2%}"]
    ]
    df_summary = pd.DataFrame(summary_data, columns=["No", "Parameter", "Satuan", "Jumlah"])
    st.dataframe(df_summary, use_container_width=True, hide_index=True)

    st.subheader("📑 Detailed Economic Model")
    
    phase_col = []
    for y in results['years']:
        if y <= exp_years:
            phase_col.append("Exploration")
        elif y <= exp_years + dev_years:
            phase_col.append("Development")
        else:
            phase_col.append("Production")

    df_det_full = pd.DataFrame({
        'Phase': phase_col,
        'Years': results['years'],
        'Prod. Rate (BOPD)': results['prod_bopd'],
        'Gross Revenue': results['gross_revenue'],
        'Total FTP': results['ftp'],
        'GR - FTP': results['gr_minus_ftp'],
        'Finding (Amort)': results['finding_amort'],
        'Depreciation': results['depreciation'],
        'Intangible (Amort)': results['intangible_amort'],
        'Opex': results['opex'],
        'Total Cost': results['total_costs_amort'],
        'Recovered': results['recovered'],
        'Unrecovered': results['unrecovered'],
        'ETS': results['ets'],
        'Gov Equity': results['gov_equity'],
        'Ctr Equity': results['ctr_equity'],
        'Gov FTP': results['gov_ftp'],
        'Ctr FTP': results['ctr_ftp'],
        'DMO Gross': results['dmo_gross'],
        'DMO Fee': results['dmo_fee'],
        'Net Ctr Share': results['net_ctr_share'],
        'Tax Paid': results['tax_paid'],
        'Cash In': results['cash_in'],
        'Cash Out': results['cash_out'],
        'Net CF': results['net_cf']
    })

    def format_zero(val):
        if val == 0:
            return "-"
        return f"{val:,.0f}"

    format_dict = {col: format_zero for col in df_det_full.columns if col not in ['Phase', 'Years']}
    st.dataframe(df_det_full.style.format(format_dict), use_container_width=True, height=500)
    
    csv_detailed = df_det_full.to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Download Detail (CSV)", csv_detailed, "PSChi_Detailed_Full.csv", "text/csv")


# ------------------------------------------
# TAB 3: SENSITIVITY ANALYSIS
# ------------------------------------------
with tab3:
    st.markdown("### 📈 Sensitivity & Risk Analysis")
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.markdown("**1. Oil Price Sensitivity**")
        st.markdown("Mensimulasikan perubahan **NPV** jika harga Minyak naik/turun dari *Base Case*.")
        
        sens_range = [-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3]
        sens_labels = ["-30%", "-20%", "-10%", "Base (0%)", "+10%", "+20%", "+30%"]
        npv_list, prices = [], []
        
        for r in sens_range:
            test_price = oil_price * (1 + r)
            prices.append(test_price)
            
            test_results = run_psc_model(override_oil_price=test_price)
            test_npv = npf.npv(discount_rate, test_results['net_cf']) / (1 + discount_rate)
            npv_list.append(test_npv)
            
        fig_sens = go.Figure()
        fig_sens.add_trace(go.Scatter(x=sens_labels, y=npv_list, mode='lines+markers', name='NPV (MUS$)', line=dict(color='royalblue', width=4), marker=dict(size=10)))
        fig_sens.update_layout(xaxis_title="Perubahan Harga Minyak", yaxis_title="NPV (MUS$)", template='plotly_white')
        st.plotly_chart(fig_sens, use_container_width=True)
        
    with col_s2:
        st.markdown("**2. NPV Profile (Discount Rate Curve)**")
        st.markdown("Melihat seberapa tahan proyek ini terhadap kenaikan suku bunga (Mencari titik persilangan IRR).")
        
        rates = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25]
        rate_labels = ["0%", "5%", "10%", "15%", "20%", "25%"]
        npv_rates = []
        for r in rates:
            val = npf.npv(r, results['net_cf']) / (1 + r)
            npv_rates.append(val)
            
        fig_npv_curve = go.Figure()
        fig_npv_curve.add_trace(go.Scatter(x=rate_labels, y=npv_rates, mode='lines+markers', name='NPV at Discount Rate', line=dict(color='purple', width=4), marker=dict(size=10)))
        fig_npv_curve.add_hline(y=0, line_dash="dash", line_color="red", annotation_text="Break-even (IRR)")
        fig_npv_curve.update_layout(xaxis_title="Discount Rate", yaxis_title="NPV (MUS$)", template='plotly_white')
        st.plotly_chart(fig_npv_curve, use_container_width=True)

# ------------------------------------------
# TAB 4: ABOUT PSChi
# ------------------------------------------
with tab4:
    st.markdown("### ℹ️ Tentang PSChi (Version 1.0)")
    st.markdown("""
    **PSChi** adalah platform simulasi interaktif untuk memodelkan keekonomian *Production Sharing Contract* (PSC) Cost Recovery. 
    Aplikasi ini dikembangkan sebagai pemenuhan tugas mata kuliah **TM3203 Manajemen dan Keekonomian Proyek** di **Program Studi Teknik Perminyakan ITB**.
    """)
    
    st.markdown("#### 👨‍🏫 Dosen Pengampu:")
    st.markdown("- Dr. Adityawarman, S.T, M.T.\n- Rafael J.S. Purba, S.T., M.T.")
    
    st.markdown("#### 👥 Tim Pengembang (Kelompok 16):")
    st.markdown("""
    1. **Ibra Rabbani Dahlan** (NIM 12223010)
    2. **Abraham Gwen Bramanti** (NIM 12223027) - *Main Developer*
    3. **Daniel Syah Putra Barus** (NIM 12223074)
    4. **Iqlima Ayarikka** (NIM 12223083)
    """)
    
    st.markdown("#### ⚙️ Metodologi & Asumsi Sistem:")
    st.info("""
    - Menggunakan skema **PSC Cost Recovery standar Indonesia**.
    - Depresiasi Capital Tangible dihitung menggunakan metode **Declining Balance**.
    - *Domestic Market Obligation* (DMO) dikalkulasi sebesar 25% dari Contractor Share Gross Revenue.
    - Pada model ini, DMO diatur efektif mulai tahun kedua produksi (Dikosongkan pada tahun pertama lifting) sesuai dengan penyesuaian arus kas proyek awal.
    """)
    
    st.markdown("#### 📧 Hubungi Kami:")
    st.markdown("Untuk masukan atau pelaporan *bug*, silakan hubungi Main Developer melalui email: [abraham.bramanti@outlook.com](mailto:abraham.bramanti@outlook.com) atau melalui [LinkedIn](https://www.linkedin.com/in/abraham-bramanti/).")

# ==========================================
# 6. FOOTER & DISCLAIMER
# ==========================================
st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: gray; font-size: 14px;'>
    <strong>Disclaimer:</strong> Hasil yang ditampilkan oleh simulator ini merupakan estimasi akademis dan simulasi analisis awal. 
    Angka-angka ini tidak dapat dijadikan landasan mutlak untuk keputusan investasi finansial final. 
    <br><br>
    Copyright © 2026 <strong>Kelompok 16 - Teknik Perminyakan ITB</strong> | PSChi v1.0
</div>
""", unsafe_allow_html=True)