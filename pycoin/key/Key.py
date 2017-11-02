from pycoin.encoding import (
    from_bytes_32, hash160, hash160_sec_to_bitcoin_address,
    is_sec_compressed, public_pair_to_sec, public_pair_to_hash160_sec,
    sec_to_public_pair, secret_exponent_to_wif
)
from pycoin.serialize import b2h
from pycoin.satoshi.der import sigencode_der, sigdecode_der


class InvalidPublicPairError(ValueError):
    pass


class InvalidSecretExponentError(ValueError):
    pass


class Key(object):

    wif_prefix = None
    sec_prefix = None
    address_prefix = None

    @classmethod
    def make_subclass(class_, wif_prefix, sec_prefix, address_prefix):

        class Key(class_):
            pass

        Key.wif_prefix = wif_prefix
        Key.sec_prefix = sec_prefix
        Key.address_prefix = address_prefix

        return Key

    def __init__(self, secret_exponent=None, generator=None, public_pair=None, hash160=None, prefer_uncompressed=None,
                 is_compressed=None, is_pay_to_script=False):
        """
        secret_exponent:
            a long representing the secret exponent
        public_pair:
            a tuple of long integers on the ecdsa curve
        hash160:
            a hash160 value corresponding to a bitcoin address

        Include at most one of secret_exponent, public_pair or hash160.

        prefer_uncompressed:
            whether or not to produce text outputs as compressed or uncompressed.

        is_pay_to_script:
            whether or not this key is for a pay-to-script style transaction

        Include at most one of secret_exponent, public_pair or hash160.
        prefer_uncompressed, is_compressed (booleans) are optional.
        """
        if is_compressed is None:
            is_compressed = False if hash160 else True
        if [secret_exponent, public_pair, hash160].count(None) != 2:
            raise ValueError("exactly one of secret_exponent, public_pair, hash160 must be passed.")
        if secret_exponent and not generator:
            raise ValueError("generator not specified when secret exponent specified")
        if prefer_uncompressed is None:
            prefer_uncompressed = not is_compressed
        self._prefer_uncompressed = prefer_uncompressed
        self._secret_exponent = secret_exponent
        self._generator = generator
        self._public_pair = public_pair
        self._hash160_uncompressed = None
        self._hash160_compressed = None
        if hash160:
            if is_compressed:
                self._hash160_compressed = hash160
            else:
                self._hash160_uncompressed = hash160

        if self._public_pair is None and self._secret_exponent is not None:
            if self._secret_exponent < 1 \
                    or self._secret_exponent >= self._generator.order():
                raise InvalidSecretExponentError()
            public_pair = self._secret_exponent * self._generator
            self._public_pair = public_pair

        if self._public_pair is not None:
            if (None in self._public_pair) or \
               (self._generator and not self._generator.contains_point(*self._public_pair)):
                raise InvalidPublicPairError()

    @classmethod
    def from_sec(class_, sec, generator):
        """
        Create a key from an sec bytestream (which is an encoding of a public pair).
        """
        public_pair = sec_to_public_pair(sec, generator)
        return class_(public_pair=public_pair, is_compressed=is_sec_compressed(sec))

    def is_private(self):
        return self.secret_exponent() is not None

    def secret_exponent(self):
        """
        Return an integer representing the secret exponent (or None).
        """
        return self._secret_exponent

    def wif(self, use_uncompressed=None, wif_prefix=None):
        """
        Return the WIF representation of this key, if available.
        If use_uncompressed is not set, the preferred representation is returned.
        """
        secret_exponent = self.secret_exponent()
        if secret_exponent is None:
            return None
        wif_prefix = wif_prefix or self.wif_prefix
        if wif_prefix is None:
            raise ValueError("wif_prefix not set")
        return secret_exponent_to_wif(secret_exponent,
                                      compressed=not self._use_uncompressed(use_uncompressed),
                                      wif_prefix=wif_prefix)

    def public_pair(self):
        """
        Return a pair of integers representing the public key (or None).
        """
        return self._public_pair

    def sec(self, use_uncompressed=None):
        """
        Return the SEC representation of this key, if available.
        If use_uncompressed is not set, the preferred representation is returned.
        """
        public_pair = self.public_pair()
        if public_pair is None:
            return None
        return public_pair_to_sec(public_pair, compressed=not self._use_uncompressed(use_uncompressed))

    def sec_as_hex(self, use_uncompressed=None, sec_prefix=None):
        """
        Return the SEC representation of this key as hex text.
        If use_uncompressed is not set, the preferred representation is returned.
        """
        sec = self.sec(use_uncompressed=use_uncompressed)
        if sec is None:
            return None
        if sec_prefix is None:
            sec_prefix = self.sec_prefix
        if sec_prefix is None:
            raise ValueError("sec_prefix not set")
        return sec_prefix + b2h(sec)

    def hash160(self, use_uncompressed=None):
        """
        Return the hash160 representation of this key, if available.
        If use_uncompressed is not set, the preferred representation is returned.
        """
        use_uncompressed = self._use_uncompressed(use_uncompressed)
        if self.public_pair() is None:
            if use_uncompressed:
                return self._hash160_uncompressed
            return self._hash160_compressed

        if use_uncompressed:
            if self._hash160_uncompressed is None:
                self._hash160_uncompressed = hash160(self.sec(use_uncompressed=use_uncompressed))
            return self._hash160_uncompressed

        if self._hash160_compressed is None:
            self._hash160_compressed = hash160(self.sec(use_uncompressed=use_uncompressed))
        return self._hash160_compressed

    def address(self, use_uncompressed=None, address_prefix=None):
        """
        Return the public address representation of this key, if available.
        If use_uncompressed is not set, the preferred representation is returned.
        """
        hash160 = self.hash160(use_uncompressed=use_uncompressed)
        if hash160:
            address_prefix = address_prefix or self.address_prefix
            if address_prefix is None:
                raise ValueError("address_prefix not set")
            return hash160_sec_to_bitcoin_address(hash160, address_prefix=address_prefix)
        return None

    bitcoin_address = address

    def as_text(self, address_prefix=None, sec_prefix=None, wif_prefix=None):
        """
        Return a textual representation of this key.
        """
        if self.secret_exponent():
            return self.wif(wif_prefix=wif_prefix)
        sec_hex = self.sec_as_hex(sec_prefix=sec_prefix)
        if sec_hex:
            return sec_hex
        return self.address(address_prefix=address_prefix)

    def public_copy(self):
        if self.secret_exponent() is None:
            return self

        return self.__class__(public_pair=self.public_pair(), prefer_uncompressed=self._prefer_uncompressed,
                             is_compressed=(self._hash160_compressed is not None))

    def subkey(self, path_to_subkey):
        """
        Return the Key corresponding to the hierarchical wallet's subkey
        """
        return self

    def subkeys(self, path_to_subkeys):
        """
        Return an iterator yielding Keys corresponding to the
        hierarchical wallet's subkey path (or just this key).
        """
        yield self

    def sign(self, h):
        """
        Return a der-encoded signature for a hash h.
        Will throw a RuntimeError if this key is not a private key
        """
        if not self.is_private():
            raise RuntimeError("Key must be private to be able to sign")
        val = from_bytes_32(h)
        r, s = self._generator.sign(self.secret_exponent(), val)
        return sigencode_der(r, s)

    def verify(self, h, sig, generator=None):
        """
        Return whether a signature is valid for hash h using this key.
        """
        generator = generator or self._generator
        if not generator:
            raise ValueError("generator must be specified")
        val = from_bytes_32(h)
        pubkey = self.public_pair()
        rs = sigdecode_der(sig)
        if self.public_pair() is None:
            # find the pubkey from the signature and see if it matches
            # our key
            possible_pubkeys = generator.possible_public_pairs_for_signature(val, rs)
            hash160 = self.hash160()
            for candidate in possible_pubkeys:
                if hash160 == public_pair_to_hash160_sec(candidate, True):
                    pubkey = candidate
                    break
                if hash160 == public_pair_to_hash160_sec(candidate, False):
                    pubkey = candidate
                    break
            else:
                # signature is using a pubkey that's not this key
                return False
        return generator.verify(pubkey, val, rs)

    def _use_uncompressed(self, use_uncompressed=None):
        if use_uncompressed:
            return use_uncompressed
        if use_uncompressed is None:
            return self._prefer_uncompressed
        return False

    def __repr__(self):
        r = self.public_copy().as_text(sec_prefix='')
        if self.is_private():
            return "private_for <%s>" % r
        return "<%s>" % r
