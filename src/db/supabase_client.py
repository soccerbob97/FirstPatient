"""Supabase client wrapper for database operations."""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Get credentials from environment
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")


class SimpleSupabaseClient:
    """Simple Supabase client using requests (avoids package import issues)."""
    
    def __init__(self, url: str, key: str):
        self.url = url.rstrip('/')
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
    
    def table(self, name: str):
        """Return a table query builder."""
        return TableQuery(self.url, self.headers, name)
    
    def rpc(self, function_name: str, params: dict = None):
        """Call a stored procedure."""
        url = f"{self.url}/rest/v1/rpc/{function_name}"
        response = requests.post(url, headers=self.headers, json=params or {})
        response.raise_for_status()
        return type('Response', (), {'data': response.json()})()


class TableQuery:
    """Simple table query builder."""
    
    def __init__(self, url: str, headers: dict, table: str):
        self.url = url
        self.headers = headers
        self.table_name = table
        self._select = "*"
        self._filters = []
        self._limit = None
    
    def select(self, columns: str):
        self._select = columns
        return self
    
    def in_(self, column: str, values: list):
        values_str = ",".join(str(v) for v in values)
        self._filters.append(f"{column}=in.({values_str})")
        return self
    
    def eq(self, column: str, value):
        self._filters.append(f"{column}=eq.{value}")
        return self
    
    def is_(self, column: str, value: str):
        self._filters.append(f"{column}=is.{value}")
        return self
    
    def ilike(self, column: str, pattern: str):
        self._filters.append(f"{column}=ilike.{pattern}")
        return self
    
    def gt(self, column: str, value):
        """Greater than filter."""
        self._filters.append(f"{column}=gt.{value}")
        return self
    
    def gte(self, column: str, value):
        """Greater than or equal filter."""
        self._filters.append(f"{column}=gte.{value}")
        return self
    
    def lt(self, column: str, value):
        """Less than filter."""
        self._filters.append(f"{column}=lt.{value}")
        return self
    
    def lte(self, column: str, value):
        """Less than or equal filter."""
        self._filters.append(f"{column}=lte.{value}")
        return self
    
    def order(self, column: str, desc: bool = False):
        """Order results by column."""
        if not hasattr(self, '_order'):
            self._order = []
        direction = ".desc" if desc else ""
        self._order.append(f"{column}{direction}")
        return self
    
    def limit(self, n: int):
        self._limit = n
        return self
    
    def execute(self):
        url = f"{self.url}/rest/v1/{self.table_name}?select={self._select}"
        for f in self._filters:
            url += f"&{f}"
        if hasattr(self, '_order') and self._order:
            url += f"&order={','.join(self._order)}"
        if self._limit:
            url += f"&limit={self._limit}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return type('Response', (), {'data': response.json()})()
    
    def update(self, data: dict):
        return UpdateQuery(self.url, self.headers, self.table_name, self._filters, data)
    
    def upsert(self, data: dict):
        url = f"{self.url}/rest/v1/{self.table_name}"
        headers = {**self.headers, "Prefer": "resolution=merge-duplicates,return=representation"}
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return type('Response', (), {'data': response.json()})()


class UpdateQuery:
    """Simple update query."""
    
    def __init__(self, url: str, headers: dict, table: str, filters: list, data: dict):
        self.url = url
        self.headers = headers.copy()
        self.headers["Prefer"] = "return=minimal"  # Don't require return data
        self.table = table
        self.filters = list(filters)
        self.data = data
    
    def eq(self, column: str, value):
        self.filters.append(f"{column}=eq.{value}")
        return self
    
    def execute(self):
        url = f"{self.url}/rest/v1/{self.table}"
        for i, f in enumerate(self.filters):
            url += ("?" if i == 0 else "&") + f
        
        # Clean data - remove None values and convert lists to proper format
        clean_data = {}
        for k, v in self.data.items():
            if v is not None:
                clean_data[k] = v
        
        response = requests.patch(url, headers=self.headers, json=clean_data)
        if response.status_code == 400:
            # Log the error for debugging
            print(f"    Update error: {response.text[:200]}")
        response.raise_for_status()
        return type('Response', (), {'data': []})()  # Return empty on success


_client = None


def get_supabase_client():
    """Get or create Supabase client singleton."""
    global _client
    if _client is None:
        _client = SimpleSupabaseClient(SUPABASE_URL, SUPABASE_KEY)
    return _client


def get_supabase_admin_client():
    """Get Supabase client with service role key for admin operations."""
    return SimpleSupabaseClient(SUPABASE_URL, SUPABASE_KEY)
