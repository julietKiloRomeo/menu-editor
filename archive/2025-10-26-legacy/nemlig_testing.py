import marimo

__generated_with = "0.14.16"
app = marimo.App(width="medium")


@app.cell
def _():
    USER = "REDACTED_EMAIL"
    PWD = "REDACTED_PASSWORD"
    return PWD, USER


@app.cell
def _():
    # nemlig_client.py
    from __future__ import annotations
    from typing import Any, Dict, List, Optional
    from dataclasses import dataclass
    from contextlib import AbstractContextManager
    import httpx
    from pydantic import BaseModel, Field
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


    # ---- Data models ----

    class Product(BaseModel):
        id: str
        name: str
        price: Optional[float] = None
        unit: Optional[str] = None
        url: Optional[str] = None
        raw: Dict[str, Any] = Field(default_factory=dict)


    class BasketItem(BaseModel):
        product_id: str
        quantity: int
        raw: Dict[str, Any] = Field(default_factory=dict)


    class Basket(BaseModel):
        items: List[BasketItem]
        total: Optional[float] = None
        raw: Dict[str, Any] = Field(default_factory=dict)


    class Order(BaseModel):
        id: str
        created: Optional[str] = None
        total: Optional[float] = None
        raw: Dict[str, Any] = Field(default_factory=dict)


    # ---- Client ----

    @dataclass
    class NemligClient(AbstractContextManager):
        """
        Thin, typed client around Nemlig's (unofficial) web API used by the website.
        Endpoints below mirror the public repo's `webapi` paths.
        """
        base_url: str = "https://www.nemlig.com"
        timeout: float = 20.0
        _client: Optional[httpx.Client] = None

        def __post_init__(self):
            if self._client is None:
                self._client = httpx.Client(
                    base_url=self.base_url,
                    timeout=self.timeout,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; NemligClient/1.0)",
                        "Accept": "application/json, text/plain, */*",
                        "Origin": self.base_url,
                        "Referer": self.base_url + "/",
                    }
                )

        # --- Lifecycle ---
        def close(self):
            if self._client:
                self._client.close()

        def __exit__(self, exc_type, exc, tb):
            self.close()

        # --- Utilities ---
        @retry(
            retry=retry_if_exception_type(httpx.HTTPError),
            wait=wait_exponential(multiplier=0.4, min=0.5, max=5),
            stop=stop_after_attempt(3),
            reraise=True,
        )
        def _get(self, path: str, **kwargs) -> httpx.Response:
            assert self._client
            return self._client.get(path, **kwargs)

        @retry(
            retry=retry_if_exception_type(httpx.HTTPError),
            wait=wait_exponential(multiplier=0.4, min=0.5, max=5),
            stop=stop_after_attempt(3),
            reraise=True,
        )
        def _post(self, path: str, json: Any = None, data: Any = None, **kwargs) -> httpx.Response:
            assert self._client
            return self._client.post(path, json=json, data=data, **kwargs)

        # ---- Auth ----
        def login(self, email: str, password: str) -> Dict[str, Any]:
            """
            Mirrors the original:

                webapi.post('/login/login', json={
                    'Username': username,
                    'Password': password,
                    'AppInstalled': False,
                    'AutoLogin': False,
                    'CheckForExistingProducts': True,
                    'DoMerge': True,
                })
            """
            payload = {
                "Username": email,
                "Password": password,
                "AppInstalled": False,
                "AutoLogin": False,
                "CheckForExistingProducts": True,
                "DoMerge": True,
            }
            resp = self._post("/webapi/login/login", json=payload)
            resp.raise_for_status()
            return resp.json()

        # ---- Search ----
        def search_products(self, query: str = "", take: int = 10) -> List[Product]:
            """
            Mirrors:

    {
    	"GET": {
    		"scheme": "https",
    		"host": "webapi.prod.knl.nemlig.it",
    		"filename": "/searchgateway/api/quick",
    		"query": {
    			"query": "bbq sauce",
    			"correlationId": "wBAr5PfX"
    		},
    		"remote": {
    			"Address": "104.18.14.135:443"
    		}
    	}
    }

                webapi.get('/s/0/1/0/Search/Search', params={'query': query, 'take': take})
            """
            resp = self._get("/webapi/s/0/1/0/Search/Search", params={"query": query, "take": take, "favorit": 1, "deliveryZoneId": 2})
            resp.raise_for_status()
            data = resp.json()

            # Best-effort mapping; fields vary so we keep `raw`.
            items = data["Products"]["Products"]
            products: List[Product] = []

            def is_available(item):
                if not "Availability" in item:
                    return False
                return item["Availability"].get("IsAvailableInStock", False) and item["Availability"].get("IsDeliveryAvailable", False)
        
            for p in filter(is_available, items):
                pid = str(p.get("Id"))
                name = p.get("Name")
                price = p.get("Price")
                unit = p.get("UnitPrice")
                url = p.get("Url")
                products.append(Product(id=pid, name=name, price=price, unit=unit, url=url, raw=p))
            return products

        # ---- Basket ----
        def add_to_basket(self, product_id: str, quantity: int = 1) -> Dict[str, Any]:
            """
            Mirrors:

                webapi.post('/basket/AddToBasket', json={'productId': product_id, 'quantity': quantity})
            """
            payload = {"productId": product_id, "quantity": quantity}
            resp = self._post("/webapi/basket/AddToBasket", json=payload)
            resp.raise_for_status()
            return resp.json()["Lines"]

        def get_basket(self) -> Basket:
            """
            Not in your snippet but exists in most clients as:
                webapi.get('/basket/GetBasket')
            """
            resp = self._get("/webapi/basket")
            resp.raise_for_status()
            data = resp.json()

            items_src = data.get("items") or data.get("Items") or []
            items = [
                BasketItem(
                    product_id=str(i.get("productId") or i.get("ProductId") or i.get("Id") or ""),
                    quantity=int(i.get("quantity") or i.get("Quantity") or 1),
                    raw=i,
                )
                for i in items_src
            ]
            total = data.get("total") or data.get("Total")
            return Basket(items=items, total=total, raw=data)

        def clear_basket(self) -> Dict[str, Any]:
            """
            Likely endpoint on the site:
                webapi.post('/basket/ClearBasket')
            """
            resp = self._post("/webapi/basket/ClearBasket")
            resp.raise_for_status()
            return resp.json()

        # ---- Orders ----
        def list_orders(self, skip: int = 0, take: int = 10) -> List[Order]:
            """
            Mirrors:

                webapi.get('/order/GetBasicOrderHistory', params={'skip': skip, 'take': take})
            """
            resp = self._get("/order/GetBasicOrderHistory", params={"skip": skip, "take": take})
            resp.raise_for_status()
            data = resp.json()
            rows = data.get("items") or data.get("Items") or data
            orders: List[Order] = []
            if isinstance(rows, list):
                for o in rows:
                    orders.append(
                        Order(
                            id=str(o.get("orderNumber") or o.get("OrderNumber") or o.get("id") or o.get("Id") or ""),
                            created=o.get("created") or o.get("CreatedDate") or o.get("Created"),
                            total=o.get("total") or o.get("Total"),
                            raw=o,
                        )
                    )
            return orders

        def get_order(self, order_number: str | int) -> Dict[str, Any]:
            """
            Mirrors:

                webapi.get('/order/GetOrderHistory', params={'orderNumber': order_number})
            """
            resp = self._get("/order/GetOrderHistory", params={"orderNumber": order_number})
            resp.raise_for_status()
            return resp.json()


        
    return (NemligClient,)


@app.cell
def _(NemligClient):
    nemlig = NemligClient()
    return (nemlig,)


@app.cell
def _(PWD, USER, nemlig):
    nemlig.login(USER, PWD)
    return


@app.cell
def _(nemlig):
    _resp = nemlig.search_products("agur")
    _resp
    return


@app.cell
def _():
    #add_response = nemlig.add_to_basket(product_id="5004144", quantity=3)
    #add_response
    return


@app.cell
def _(nemlig):
    nemlig.get_basket()
    return


if __name__ == "__main__":
    app.run()
