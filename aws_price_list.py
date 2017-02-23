#!/usr/bin/env python

import json
import datetime
from urllib.request import urlopen, urljoin


class AWSOffersIndex:
    """Represent AWS offer index file and its information"""

    @property
    def format(self):
        """Return formatVersion of the offer index file"""
        return self._idx.get('formatVersion')

    @property
    def disclaimer(self):
        """Return disclaimer of the offer index file"""
        return self._idx.get('disclaimer')

    @property
    def published(self):
        """Return publicationDate of the offer index file as a datetime object
        """
        pbd = self._idx.get('publicationDate')
        if pbd.endswith('Z'):
            return datetime.datetime.strptime(pbd.replace('Z', '+0000'),
                                              '%Y-%m-%dT%H:%M:%S%z')
        else:
            raise ValueError(
                '%s: Unsupported format for publicationDate' % pbd)

    @property
    def accessed(self):
        """Datetime object when the offer index information was accessed"""
        return self._accessed

    @property
    def offers(self):
        """List of available offers to retrieve"""
        return self._idx.get('offers').keys()

    @property
    def endpoint(self):
        """URL of the AWS offer index JSON file."""
        return self._idx_url

    def reload(self):
        """Reload the offer index JSON file."""
        with urlopen(self._idx_url) as r:
            self._idx = json.loads(r.read().decode('utf-8'))
        self._accessed = datetime.datetime.now(datetime.timezone.utc)

    def __init__(self):
        self._idx_url = ('https://pricing.us-east-1.amazonaws.com'
                         '/offers/v1.0/aws/index.json')
        self.reload()

    def offer(self, offer_code):
        """Return an AWSOffer object for the supplied offer_code"""
        try:
            offr_urlpath = self._idx['offers'][offer_code]['currentVersionUrl']
        except KeyError:
            raise ValueError('%s: Unknown offer code' % offer_code)
        offr_url = urljoin(self._idx_url, offr_urlpath)
        return AWSOffer(offr_url)


class AWSOffer:
    """Represent a single AWS offer and its prices & terms"""

    @property
    def format(self):
        """Return formatVersion of the offer index file"""
        return self._offr.get('formatVersion')

    @property
    def disclaimer(self):
        """Return disclaimer of the offer index file"""
        return self._offr.get('disclaimer')

    @property
    def published(self):
        """Return publicationDate of the offer index file as a datetime object
        """
        return self._pubdate

    @property
    def accessed(self):
        """Datetime object when the offer information was accessed"""
        return self._accessed

    @property
    def code(self):
        """Return offer's code"""
        return self._offr.get('offerCode')

    @property
    def version(self):
        """Return offer's version"""
        return self._offr.get('version')

    @property
    def products(self):
        """List of available products in the AWS offer"""
        return self._offr.get('products').keys()

    @property
    def terms(self):
        """List of offer's terms available"""
        return self._offr['terms'].keys()

    @property
    def endpoint(self):
        """URL of the AWS offer JSON file."""
        return self._url

    def reload(self):
        """Reload the offer JSON file."""
        with urlopen(self._url) as r:
            self._offr = json.loads(r.read().decode('utf-8'))
        self._accessed = datetime.datetime.now(datetime.timezone.utc)

    def __init__(self, url):
        self._url = url
        self.reload()
        pbd = self._offr.get('publicationDate')
        if pbd.endswith('Z'):
            self._pubdate = datetime.datetime.strptime(
                pbd.replace('Z', '+0000'), '%Y-%m-%dT%H:%M:%S%z')
        else:
            raise ValueError(
                '%s: Unsupported format for publicationDate' % pbd)

    def product(self, sku, term_type='OnDemand'):
        """Return AWS produt information as AWSProduct object"""
        # Sanity check...
        if sku != self._offr['products'][sku]['sku']:
            raise ValueError('Product SKU mismatch')
        return AWSProduct(self._offr['products'][sku],
                          self._offr['terms'][term_type][sku], term_type)


class AWSProduct:
    """Represent one AWS product's prices and terms"""

    @property
    def sku(self):
        """Return AWS product's SKU"""
        return self._sku['sku']

    @property
    def family(self):
        """AWS product's family"""
        return self._sku['productFamily']

    @property
    def attributes(self):
        """AWS product's attributes as a dict"""
        return self._sku['attributes']

    @property
    def term_type(self):
        """AWS product's term type"""
        return self._term_type

    @property
    def pricing(self):
        """Product's pricing information as a list of AWSProductPricing objects
        """
        return self._pricing

    def __init__(self, sku_info, sku_terms, term_type):
        if not (isinstance(sku_info, dict) and isinstance(sku_terms, dict)):
            raise TypeError('SKU and its terms information not dicts')
        self._sku = sku_info
        self._term_type = term_type
        self._pricing = list()

        # Generate AWSProductPricing object for each entry in SKU's pricing
        # terms...
        for v in sku_terms.values():
            self._pricing.append(AWSProductPricing(v))


class AWSProductPricing:
    """Represent pricing (terms) of one AWS product"""

    @property
    def code(self):
        """AWS product's offer term code"""
        return self._code

    @property
    def product_sku(self):
        """AWS product SKU this term belongs to"""
        return self._product_sku

    @property
    def attributes(self):
        """AWS product's term attributes as a dict"""
        return self._attributes

    @property
    def effective_from(self):
        """AWS product term's effective from date as a datetime object"""
        return self._from_date

    @property
    def tiers(self):
        """Return product prices as a list of AWSProductPriceTier objects"""
        return self._tiers

    def get_price(self, amount):
        """Calculate the price for the given amount.

        The value of amount is assumed to be in the correct units.
        """
        price = 0

        # Iterate over price tiers...
        for t in self._tiers:
            if amount > t.end_range:
                price += t.price * (t.end_range - t.begin_range)
            else:
                price += t.price * (amount - t.begin_range)
                break

        return price

    @property
    def price_unit(self):
        """Get the unit of the price tiers.

        Assumption is there is only one unit value. Exception thrown if tiers
        have different units.
        """
        unit = set(t.unit for t in self._tiers)
        if len(unit) != 1:
            raise ValueError('More than one unit for price tiers')
        else:
            return unit.pop()

    def __init__(self, term):
        if not isinstance(term, dict):
            raise TypeError('AWS product terms information not in a dict')

        self._code = term['offerTermCode']
        self._product_sku = term['sku']
        self._attributes = term['termAttributes']
        self._from_date = term['effectiveDate']
        if self._from_date.endswith('Z'):
            self._from_date = datetime.datetime.strptime(
                self._from_date.replace('Z', '+0000'), '%Y-%m-%dT%H:%M:%S%z')
        else:
            raise ValueError(
                '%s: Unsupported format for effective date' % self._from_date)

        # Convert term prices into a list of AWSProductPriceTier objects...
        self._tiers = list()
        for v in term['priceDimensions'].values():
            self._tiers.append(AWSProductPriceTier(v))

        # Sort tier prices on the begin range value...
        self._tiers.sort(key=lambda t: t.begin_range)


class AWSProductPriceTier:
    """Represent one AWS product's price tier"""

    @property
    def rate_code(self):
        """Product's price rate code"""
        return self._info['rateCode']

    @property
    def description(self):
        return self._info['description']

    @property
    def unit(self):
        return self._info['unit']

    @property
    def applies_to(self):
        return self._info['appliesTo']

    @property
    def price(self):
        """AWS product tier's price per unit"""
        return self._info['pricePerUnit']['USD']

    @property
    def begin_range(self):
        """The lowest usage amount to which this pricing tier applies"""
        return self._info['beginRange']

    @property
    def end_range(self):
        """The highest usage amount to which this pricing tier applies"""
        return self._info['endRange']

    def __init__(self, arg):
        if not isinstance(arg, dict):
            raise TypeError('Product price information not in a dict')
        self._info = arg

        if 'USD' in self._info['pricePerUnit']:
            self._info['pricePerUnit']['USD'] = float(
                self._info['pricePerUnit']['USD'])
        else:
            raise ValueError('No price in US$')

        self._info['beginRange'] = float(self._info['beginRange'])
        self._info['endRange'] = float(self._info['endRange'])
