"""Yahoo Finance API client for fetching financial data.

This module provides functions to fetch financial data from Yahoo Finance
using the yfinance library. It follows patterns from src/tools/api.py.

Functions:
- get_prices_yfinance: Fetch historical price data
- get_financial_metrics_yfinance: Fetch financial metrics
- search_line_items_yfinance: Fetch line items from financial statements
- get_insider_trades_yfinance: Fetch insider trading data
- get_company_news_yfinance: Fetch company news
- get_market_cap_yfinance: Fetch market capitalization
"""

import pandas as pd

# Check if yfinance is available
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

from src.data.models import (
    CompanyNews,
    FinancialMetrics,
    Price,
    LineItem,
    InsiderTrade,
)


def get_prices_yfinance(ticker: str, start_date: str, end_date: str) -> list[Price]:
    """Fetch price data from Yahoo Finance using yfinance."""
    if not YFINANCE_AVAILABLE:
        raise Exception("yfinance is not installed. Please install it with: pip install yfinance")
    
    try:
        # Download data from yfinance
        data = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=False)
        
        if data.empty:
            return []
        
        # Convert to our Price model format
        prices = []
        for date_idx, row in data.iterrows():
            # Extract scalar values to avoid FutureWarning about calling float on Series
            open_val = row['Open'].item() if hasattr(row['Open'], 'item') else float(row['Open'])
            high_val = row['High'].item() if hasattr(row['High'], 'item') else float(row['High'])
            low_val = row['Low'].item() if hasattr(row['Low'], 'item') else float(row['Low'])
            close_val = row['Close'].item() if hasattr(row['Close'], 'item') else float(row['Close'])
            volume_val = row['Volume'].item() if hasattr(row['Volume'], 'item') else int(row['Volume'])
            
            price = Price(
                open=open_val,
                high=high_val,
                low=low_val,
                close=close_val,
                volume=volume_val,
                time=date_idx.strftime('%Y-%m-%d')
            )
            prices.append(price)
        
        return prices
        
    except Exception as e:
        raise Exception(f"Error fetching data from Yahoo Finance for {ticker}: {str(e)}")


def get_financial_metrics_yfinance(ticker: str, end_date: str = None) -> list[FinancialMetrics]:
    """Fetch financial metrics from Yahoo Finance using yfinance."""
    if not YFINANCE_AVAILABLE:
        raise Exception("yfinance is not installed. Please install it with: pip install yfinance")
    
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info
        
        # Defensive check: ensure info is a dict and not None
        if not info or not isinstance(info, dict):
            raise Exception(f"No valid info data returned for ticker {ticker}")
        
        # Helper function to safely get numeric values
        def safe_get_numeric(key: str, default=None):
            """Safely get numeric values from info dict, handling None cases."""
            value = info.get(key, default)
            # Ensure we don't pass None where a number is expected for calculations
            if value is None:
                return None
            try:
                # Ensure it's a valid number
                return float(value) if value is not None else None
            except (ValueError, TypeError):
                return None
        
        # Helper function to safely get string values  
        def safe_get_string(key: str, default='USD'):
            """Safely get string values from info dict."""
            value = info.get(key, default)
            if value is None:
                return default
            try:
                str_value = str(value)
                # Ensure the string is not empty and contains valid characters
                return str_value if str_value and str_value.strip() else default
            except (ValueError, TypeError):
                return default
        
        # Create a single FinancialMetrics object with available data
        metric = FinancialMetrics(
            ticker=ticker,
            report_period="ttm",
            period="ttm",
            currency=safe_get_string('currency', 'USD'),
            
            # Valuation metrics
            market_cap=safe_get_numeric('marketCap'),
            enterprise_value=safe_get_numeric('enterpriseValue'),
            price_to_earnings_ratio=safe_get_numeric('trailingPE'),
            price_to_book_ratio=safe_get_numeric('priceToBook'),
            price_to_sales_ratio=safe_get_numeric('priceToSalesTrailing12Months'),
            enterprise_value_to_ebitda_ratio=safe_get_numeric('enterpriseToEbitda'),
            enterprise_value_to_revenue_ratio=safe_get_numeric('enterpriseToRevenue'),
            
            # Set unavailable fields to None
            free_cash_flow_yield=None,
            peg_ratio=safe_get_numeric('pegRatio'),
            
            # Profitability metrics
            gross_margin=safe_get_numeric('grossMargins'),
            operating_margin=safe_get_numeric('operatingMargins'),
            net_margin=safe_get_numeric('profitMargins'),  # profit_margin is same as net_margin
            
            # Returns
            return_on_equity=safe_get_numeric('returnOnEquity'),
            return_on_assets=safe_get_numeric('returnOnAssets'),
            return_on_invested_capital=None,  # Not available in yfinance
            
            # Efficiency metrics (not available in yfinance info)
            asset_turnover=None,
            inventory_turnover=None,
            receivables_turnover=None,
            days_sales_outstanding=None,
            operating_cycle=None,
            working_capital_turnover=None,
            
            # Liquidity metrics
            current_ratio=safe_get_numeric('currentRatio'),
            quick_ratio=safe_get_numeric('quickRatio'),
            cash_ratio=None,  # Not available in yfinance
            operating_cash_flow_ratio=None,  # Not available in yfinance
            
            # Leverage metrics
            debt_to_equity=safe_get_numeric('debtToEquity'),
            debt_to_assets=None,  # Not available in yfinance
            interest_coverage=None,  # Not available in yfinance
            
            # Growth metrics
            revenue_growth=safe_get_numeric('revenueGrowth'),
            earnings_growth=safe_get_numeric('earningsGrowth'),
            book_value_growth=None,  # Not available in yfinance
            earnings_per_share_growth=None,  # Not available in yfinance
            free_cash_flow_growth=None,  # Not available in yfinance
            operating_income_growth=None,  # Not available in yfinance
            ebitda_growth=None,  # Not available in yfinance
            
            # Other metrics
            payout_ratio=safe_get_numeric('payoutRatio'),
            earnings_per_share=safe_get_numeric('trailingEps'),
            book_value_per_share=safe_get_numeric('bookValue'),
            free_cash_flow_per_share=None,  # Not available in yfinance
        )
        
        return [metric] if metric else []
        
    except Exception as e:
        raise Exception(f"Error fetching financial metrics from Yahoo Finance for {ticker}: {str(e)}")


def search_line_items_yfinance(
    ticker: str,
    line_items: list[str],
    end_date: str = None,
    period: str = "ttm",
    limit: int = 10,
) -> list[LineItem]:
    """Fetch line items from Yahoo Finance using yfinance."""
    if not YFINANCE_AVAILABLE:
        raise Exception("yfinance is not installed. Please install it with: pip install yfinance")
    
    try:
        ticker_obj = yf.Ticker(ticker)
        
        # Get financial statements based on period
        if period == "ttm" or period == "annual":
            income_stmt = ticker_obj.income_stmt
            balance_sheet = ticker_obj.balance_sheet
            cashflow = ticker_obj.cashflow
        else:
            income_stmt = ticker_obj.quarterly_income_stmt
            balance_sheet = ticker_obj.quarterly_balance_sheet
            cashflow = ticker_obj.quarterly_cashflow
        
        # Mapping of common line items to yfinance field names
        line_item_mapping = {
            # Revenue & Income
            "revenue": "Total Revenue",
            "total_revenue": "Total Revenue", 
            "net_income": "Net Income",
            "operating_income": "Operating Income",
            "ebit": "EBIT",
            "ebitda": "EBITDA",
            "gross_margin": "Gross Profit",
            "operating_margin": "Operating Income",
            
            # Per Share Metrics
            "earnings_per_share": "Diluted EPS",
            "book_value_per_share": "Stockholders Equity",
            "outstanding_shares": "Share Issued",
            
            # Balance Sheet Items
            "total_assets": "Total Assets",
            "total_liabilities": "Total Liabilities Net Minority Interest",
            "current_assets": "Current Assets",
            "current_liabilities": "Current Liabilities",
            "cash_and_equivalents": "Cash And Cash Equivalents",
            "total_debt": "Total Debt",
            "goodwill_and_intangible_assets": "Goodwill And Other Intangible Assets",
            "intangible_assets": "Other Intangible Assets",
            "shareholders_equity": "Stockholders Equity",
            
            # Cash Flow Items
            "free_cash_flow": "Free Cash Flow",
            "capital_expenditure": "Capital Expenditure",
            "depreciation_and_amortization": "Depreciation And Amortization",
            "dividends_and_other_cash_distributions": "Cash Dividends Paid",
            "issuance_or_purchase_of_equity_shares": "Common Stock Issuance",
            
            # Expense Items
            "operating_expense": "Total Expenses",
            "research_and_development": "Research And Development",
            "interest_expense": "Interest Expense",
            
            # Financial Ratios & Metrics (these come from financial metrics API, not line items)
            "debt_to_equity": "Total Debt",  # Will need calculation
            "asset_turnover": None,  # Not available in line items
            "beta": None,  # Not available in line items
            "ev_to_ebit": None,  # Not available in line items
            "return_on_invested_capital": None,  # Not available in line items
        }
        
        # Get all unique periods from the data
        all_periods = set()
        if income_stmt is not None and not income_stmt.empty:
            all_periods.update(income_stmt.columns)
        if balance_sheet is not None and not balance_sheet.empty:
            all_periods.update(balance_sheet.columns)
        if cashflow is not None and not cashflow.empty:
            all_periods.update(cashflow.columns)
        
        # Sort periods (most recent first)
        sorted_periods = sorted(all_periods, reverse=True)[:limit]
        
        results = []
        
        for period_date in sorted_periods:
            line_item_data = {
                "ticker": ticker,
                "report_period": str(period_date.date()) if hasattr(period_date, 'date') else str(period_date),
                "period": period,
                "currency": 'USD',  # Default currency
            }
            
            # Collect all requested line items for this period
            for item in line_items:
                yfinance_name = line_item_mapping.get(item, item)
                value = None
                
                # Skip if yfinance_name is None (not available in yfinance)
                if yfinance_name is None:
                    continue
                
                # Search in income statement first
                if income_stmt is not None and yfinance_name in income_stmt.index and period_date in income_stmt.columns:
                    value = income_stmt.loc[yfinance_name, period_date]
                
                # Then balance sheet
                elif balance_sheet is not None and yfinance_name in balance_sheet.index and period_date in balance_sheet.columns:
                    value = balance_sheet.loc[yfinance_name, period_date]
                
                # Then cash flow
                elif cashflow is not None and yfinance_name in cashflow.index and period_date in cashflow.columns:
                    value = cashflow.loc[yfinance_name, period_date]
                
                # Add to line_item_data if value is valid
                if value is not None and not pd.isna(value):
                    line_item_data[item] = float(value)
            
            # Only create LineItem if we have at least one valid value
            if len(line_item_data) > 4:  # More than just the base fields
                line_item = LineItem(**line_item_data)
                results.append(line_item)
        
        return results
        
    except Exception as e:
        raise Exception(f"Error fetching line items from Yahoo Finance for {ticker}: {str(e)}")


def get_insider_trades_yfinance(
    ticker: str,
    end_date: str = None,
    start_date: str = None,
    limit: int = 1000,
) -> list[InsiderTrade]:
    """Fetch insider trades from Yahoo Finance using yfinance."""
    if not YFINANCE_AVAILABLE:
        raise Exception("yfinance is not installed. Please install it with: pip install yfinance")
    
    try:
        ticker_obj = yf.Ticker(ticker)
        insider_data = ticker_obj.insider_transactions
        
        if insider_data is None or insider_data.empty:
            return []
        
        trades = []
        for _, row in insider_data.iterrows():
            # Basic data mapping - yfinance has limited insider trade details
            trade = InsiderTrade(
                ticker=ticker,
                issuer=None,  # Not available in yfinance
                name=str(row.get('Insider', '')),
                title=str(row.get('Position', '')),
                is_board_director=None,  # Not available in yfinance
                transaction_date=str(row.get('Start Date', '')),
                transaction_shares=int(row.get('Shares', 0)) if pd.notnull(row.get('Shares')) else 0,
                transaction_price_per_share=None,  # Not available in yfinance
                transaction_value=float(row.get('Value', 0)) if pd.notnull(row.get('Value')) else 0.0,
                shares_owned_before_transaction=None,  # Not available in yfinance
                shares_owned_after_transaction=None,  # Not available in yfinance
                security_title=None,  # Not available in yfinance
                filing_date=str(row.get('Start Date', '')),  # Use same date for filing
            )
            trades.append(trade)
        
        return trades[:limit]
        
    except Exception as e:
        # Return empty list instead of raising exception for non-critical data
        print(f"Warning: Could not fetch insider trades from Yahoo Finance for {ticker}: {str(e)}")
        return []


def get_company_news_yfinance(
    ticker: str,
    end_date: str = None,
    start_date: str = None,
    limit: int = 1000,
) -> list[CompanyNews]:
    """Fetch company news from Yahoo Finance using yfinance."""
    if not YFINANCE_AVAILABLE:
        raise Exception("yfinance is not installed. Please install it with: pip install yfinance")
    
    try:
        ticker_obj = yf.Ticker(ticker)
        news_data = ticker_obj.news
        
        if not news_data:
            return []
        
        news_items = []
        for item in news_data[:limit]:
            content = item.get('content', {})
            if content:
                news = CompanyNews(
                    ticker=ticker,
                    title=content.get('title', ''),
                    author='',  # yfinance doesn't provide author info
                    source=content.get('publisher', {}).get('name', '') if isinstance(content.get('publisher'), dict) else str(content.get('publisher', '')),
                    url=content.get('clickThroughUrl', {}).get('url', '') if isinstance(content.get('clickThroughUrl'), dict) else str(content.get('clickThroughUrl', '')),
                    date=content.get('publishedAt', ''),
                    sentiment='neutral'  # yfinance doesn't provide sentiment
                )
                news_items.append(news)
        
        return news_items
        
    except Exception as e:
        # Return empty list instead of raising exception for non-critical data
        print(f"Warning: Could not fetch company news from Yahoo Finance for {ticker}: {str(e)}")
        return []


def get_market_cap_yfinance(ticker: str, end_date: str = None) -> float | None:
    """Fetch market cap from Yahoo Finance using yfinance."""
    if not YFINANCE_AVAILABLE:
        raise Exception("yfinance is not installed. Please install it with: pip install yfinance")
    
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info
        return info.get('marketCap')
        
    except Exception as e:
        print(f"Warning: Could not fetch market cap from Yahoo Finance for {ticker}: {str(e)}")
        return None
