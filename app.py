import streamlit as st
import gspread
import pandas as pd
# IMPORTANT: Added the 'secrets' import for secure deployment
from streamlit import secrets 
from google.oauth2.service_account import Credentials
import os 

# --- Google Sheets Setup ---
SHEET_NAME = "App 2025 Finances"
# NOTE: The CREDENTIALS_FILE variable is no longer used, as we rely on secrets.

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# --- Load Credentials SECURELY ---
try:
    # Use Streamlit's secure secrets management for deployment
    # We construct the credentials dictionary directly from st.secrets['gspread']
    
    # 1. Build the dictionary from Streamlit secrets
    creds_dict = {
        "type": st.secrets["gspread"]["type"],
        "project_id": st.secrets["gspread"]["project_id"],
        "private_key_id": st.secrets["gspread"]["private_key_id"],
        # 2. Crucial fix: Replace the string '\n' with an actual newline character
        "private_key": st.secrets["gspread"]["private_key"].replace('\\n', '\n'),
        "client_email": st.secrets["gspread"]["client_email"],
        "client_id": st.secrets["gspread"]["client_id"],
        "auth_uri": st.secrets["gspread"]["auth_uri"],
        "token_uri": st.secrets["gspread"]["token_uri"],
        "auth_provider_x509_cert_url": st.secrets["gspread"]["auth_provider_x509_cert_url"],
        "client_x509_cert_url": st.secrets["gspread"]["client_x509_cert_url"],
        "universe_domain": st.secrets["gspread"]["universe_domain"]
    }
    
    # 3. Create Credentials object from the dictionary
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=scope
    )
except KeyError:
    st.error("❌ The Google Sheets credentials (secrets) were not found in Streamlit Cloud. Please ensure the 'gspread' section in `.streamlit/secrets.toml` is correct.")
    st.stop()
except Exception as e:
    st.error(f"❌ An error occurred while loading credentials: {e}")
    st.stop()


# Authorize gspread client (runs on every rerun)
client = gspread.authorize(creds)


# --- CACHED FUNCTION 1: Load Sheet Data (Headers and Accounts) ---
@st.cache_data(ttl=300) # Cache for 5 minutes
def load_transaction_data(_client):
    # Fetch data using the client but don't return the sheet object (avoiding auth errors)
    temp_sheet = _client.open(SHEET_NAME).worksheet("TRNSX")
    all_sheet_headers = temp_sheet.row_values(4)
    accounts = all_sheet_headers[4:15]  # E4 to O4
    accounts = [acc for acc in accounts if acc.strip()]
    return all_sheet_headers, accounts

# --- CACHED FUNCTION 2: Load Categories (Dynamic Segments) ---
@st.cache_data(ttl=300) # Cache for 5 minutes
def load_categories(_client):
    try:
        stat_sheet = _client.open(SHEET_NAME).worksheet("Stat")
        all_categories = stat_sheet.col_values(1)

        # A9:A37 (Expense) -> Python index [8:37]
        expense_categories = [cat for cat in all_categories[8:37] if cat.strip()]
        
        # A39:A43 (Income) -> Python index [38:43]
        income_categories = [cat for cat in all_categories[38:43] if cat.strip()]
        
        # A48:A55 (Invest) -> Python index [47:55]
        invest_categories = [cat for cat in all_categories[47:55] if cat.strip()]
        
        return expense_categories, income_categories, invest_categories
        
    except Exception as e:
        st.warning(f"Could not load categories from Stat tab: {e}")
        return [], [], []

# --- Run Cached Loaders ---
all_sheet_headers, accounts = load_transaction_data(client)
expense_categories, income_categories, invest_categories = load_categories(client)


# --- Streamlit UI ---
# Mobile-Optimized Layout: No sidebar, all inputs in the main column.
st.set_page_config(page_title="Finance Quick Entry", page_icon="💸", layout="centered")

st.title("💸 Finance Quick Entry")
st.write("Easily add a transaction to your Google Sheet.")

st.header("🧾 New Transaction Entry")

# All inputs are now in the main column (mobile-friendly flow)
date = st.date_input("Date")
trans_type = st.selectbox("Transaction Type", ["EXPENSE", "INCOME", "TRNSFR", "INVST"])

# --- Category logic (dynamic based on trans_type) ---
category = ""
if trans_type == "EXPENSE":
    if not expense_categories:
        st.warning("Expense categories failed to load.")
    category = st.selectbox("Category (Expense)", expense_categories)
    st.markdown('---') 
elif trans_type == "INCOME":
    if not income_categories:
        st.warning("Income categories failed to load.")
    category = st.selectbox("Category (Income)", income_categories)
    st.markdown('---') 
elif trans_type == "INVST":
    if not invest_categories:
        st.warning("Investment categories failed to load.")
    category = st.selectbox("Category (Invest)", invest_categories)
    st.markdown('---') 
else: # TRNSFR
    # Category remains blank
    pass 
# --- End Category logic ---
    
note = st.text_input("Description / Note")

# --- Initialization of Variables ---
from_account = None
to_account = None
account_for_single_transactions = None
transfer_fee_amount = 0.0
amount_input = 0.0 
# --- End Initialization ---

# Conditional Account Selection for TRNSFR
if trans_type == "TRNSFR":
    
    # 1. Account Selection
    col1, col2 = st.columns(2)
    
    with col1:
        from_account = st.selectbox("From Account (Debit)", accounts, key='from_acc')
    
    # Filter out the 'from' account for the 'to' account selection
    to_accounts_filtered = [acc for acc in accounts if acc != from_account]
    
    if not to_accounts_filtered:
        st.error("❌ Cannot perform transfer: Only one account available.")
        st.stop()

    with col2:
        to_account = st.selectbox("To Account (Credit)", to_accounts_filtered, key='to_acc')
        
    st.markdown('---') 
    
    # 2. Amount Input (Moved to appear before fee)
    amount_input = st.number_input("Amount (Positive Value)", min_value=0.0, step=0.01, help="Enter the transfer amount.")
    
    # 3. Transfer Fee Option
    transfer_fee_check = st.checkbox("Add Transfer Fee?", key='fee_check')
    
    if transfer_fee_check:
        transfer_fee_amount = st.number_input("Fee Amount (Positive Value)", 
                                                      min_value=0.0, step=0.01, value=0.0, key='fee_amount')
        st.info(f"Fee will be added to the debited amount from **{from_account}**.")
    
else:
    account_for_single_transactions = st.selectbox("Account", accounts, key='single_acc')
    # Amount input for non-TRNSFR transactions
    amount_input = st.number_input("Amount (Positive Value)", min_value=0.0, step=0.01, help="Enter a positive number. Decimals optional.")


# FIX: Ensure the st.button call is complete
if st.button("➕ Add Transaction", use_container_width=True):
    try:
        # 1. Validation
        if amount_input == 0.0:
            st.error("❌ Amount cannot be zero.")
            st.stop()
        
        if trans_type == "TRNSFR" and (from_account is None or to_account is None):
            st.error("❌ Please select valid accounts for the transfer.")
            st.stop()
        
        # --- FIX: Get a fresh sheet object immediately before writing/reading for next_row ---
        sheet = client.open(SHEET_NAME).worksheet("TRNSX")
        # --- End FIX ---

        # 2. Determine base numerical value
        amount_numerical = amount_input
        
        # 3. Prepare display string (for success message)
        success_amount_display = f"₱{amount_numerical:,.2f}"

        # Find the first empty row in Column A (Date)
        col_a = sheet.col_values(1) 
        next_row = len(col_a) + 1  # first blank after last filled A cell

        # Apply desired date format
        formatted_date = date.strftime("%#d %b %Y") if os.name == 'nt' else date.strftime("%-d %b %Y")
        if not formatted_date or formatted_date.startswith('0'):
            # Fallback/Safe format:
            formatted_date = date.strftime("%d %b %Y").lstrip('0')
            
        # Prepare row with blanks. We need 15 columns (A-O) for input data.
        ROW_DATA_LENGTH = 15 # A=1, B=2, ... O=15
        row_data = [""] * ROW_DATA_LENGTH 
        
        row_data[0] = formatted_date     # Date (A)
        row_data[1] = trans_type         # Type (B)
        row_data[2] = category           # Category (C)
        row_data[3] = note               # Note (D)
        
        success_msg = ""
        
        # 4. Handle single or dual account transactions
        if trans_type == "TRNSFR":
            
            # Apply fee to the debited amount
            debit_amount = amount_numerical + transfer_fee_amount
            credit_amount = amount_numerical
            
            # Negative amount (Debit) to From Account
            if from_account in all_sheet_headers:
                from_acc_index = all_sheet_headers.index(from_account)
                if 0 <= from_acc_index < ROW_DATA_LENGTH:
                     row_data[from_acc_index] = -debit_amount # Write negative float (Original + Fee)
            
            # Positive amount (Credit) to To Account
            if to_account in all_sheet_headers:
                to_acc_index = all_sheet_headers.index(to_account)
                if 0 <= to_acc_index < ROW_DATA_LENGTH:
                     row_data[to_acc_index] = credit_amount # Write positive float (Original)
            
            if transfer_fee_amount > 0:
                 fee_display = f" (Fee: ₱{transfer_fee_amount:,.2f} applied to debit, total debit: ₱{-debit_amount:,.2f})"
            else:
                fee_display = ""
                
            success_msg = f"✅ Added {trans_type} of {success_amount_display} from **{from_account}** to **{to_account}**.{fee_display}"
            
        elif account_for_single_transactions in all_sheet_headers:
            # EXPENSE, INCOME, INVST Logic: Write one amount
            
            amount_to_write = amount_numerical
            
            # TWEAK: Handle negative sign for EXPENSE and INVST
            if trans_type == "EXPENSE" or trans_type == "INVST":
                amount_to_write = -amount_numerical
                st.info(f"Automatically converting amount to **negative** for **{trans_type}**.")
            
            # Write amount to the single account column
            account_index = all_sheet_headers.index(account_for_single_transactions)
            if 0 <= account_index < ROW_DATA_LENGTH:
                 row_data[account_index] = amount_to_write # Write the float (already signed)
            else:
                st.warning(f"Account column '{account_for_single_transactions}' is outside the writable range (A-O) and was skipped.")
                
            success_msg = f"✅ Added {trans_type} of {success_amount_display} to **{account_for_single_transactions}** under {category}."
        
        else:
            st.error("❌ Account not found or selected.")
            st.stop()


        # Write range limited to A through O (the 15th column) to protect Column P formulas
        WRITE_END_COLUMN = 'O'
        cell_range = f"A{next_row}:{WRITE_END_COLUMN}{next_row}"
        
        # We write only the first 15 elements of row_data
        sheet.update(cell_range, [row_data])

        # Display success message (this triggers a rerun, which reloads the table below)
        st.success(success_msg)
        
    except Exception as e:
        st.error(f"❌ Error adding transaction: {e}")

st.markdown("---")

# --- Display last 5 transactions (Stable Table View) ---
# FIX: Get a fresh sheet object immediately before reading
try:
    sheet = client.open(SHEET_NAME).worksheet("TRNSX")
    data = sheet.get_all_values()
    sheet_headers = data[3]  # Row 4 from sheet

    # --- Create a unique, cleaned list of headers (required for DataFrame) ---
    if len(sheet_headers) >= 4:
        sheet_headers[0] = 'Date'
        sheet_headers[1] = 'Type'
        sheet_headers[2] = 'Category'
        sheet_headers[3] = 'Note'

    final_headers = []
    seen = set()
    for i, name in enumerate(sheet_headers):
        if not name.strip():
            name = f"Col_{i+1}"

        original_name = name
        k = 1
        while name in seen:
            name = f"{original_name}_{k}"
            k += 1

        final_headers.append(name)
        seen.add(name)
    # --- End Header Cleaning ---

    data_rows = data[4:]
    
    # Filter out blank rows based on Column A (Date)
    valid_data_rows = [row for row in data_rows if row and str(row[0]).strip()]
    
    st.subheader("📊 Last 5 Transactions")
    
    if valid_data_rows:
        # Resilient DataFrame Creation
        max_row_width = max(len(row) for row in valid_data_rows)
        df = pd.DataFrame(valid_data_rows, columns=final_headers[:max_row_width])
        
        # Get the last 5 transactions and display
        st.dataframe(df.tail(5).iloc[::-1], use_container_width=True) # Show last 5, reversed for newest first
    else:
        st.write("No valid transactions found to display.")
        
except Exception as e:
    # If the transaction list fails to load, show a warning, but don't stop the whole app
    st.warning(f"Could not load recent transactions: {e}")