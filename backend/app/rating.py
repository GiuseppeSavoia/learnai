"""Glicko-2 (Glickman, 2012) applicato a una singola partita/puzzle per periodo di rating."""

from __future__ import annotations

import math
from dataclasses import dataclass

SCALE = 173.7178
TAU = 0.5
EPSILON = 1e-6
MIN_RD = 45.0
MAX_RD = 350.0
DEFAULT_VOLATILITY = 0.06


@dataclass(frozen=True)
class Rating:
    rating: float
    rd: float
    volatility: float = DEFAULT_VOLATILITY


def _g(phi: float) -> float:
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _expected(mu: float, mu_j: float, phi_j: float) -> float:
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def expected_score(player: Rating, opponent: Rating) -> float:
    mu = (player.rating - 1500.0) / SCALE
    mu_j = (opponent.rating - 1500.0) / SCALE
    return _expected(mu, mu_j, opponent.rd / SCALE)


def update(player: Rating, opponent: Rating, score: float) -> Rating:
    """Nuovo rating del giocatore dopo un risultato `score` (1 vittoria, 0.5 patta, 0 sconfitta)."""
    mu = (player.rating - 1500.0) / SCALE
    phi = player.rd / SCALE
    sigma = player.volatility
    mu_j = (opponent.rating - 1500.0) / SCALE
    phi_j = opponent.rd / SCALE

    g_j = _g(phi_j)
    e_j = _expected(mu, mu_j, phi_j)
    v = 1.0 / (g_j * g_j * e_j * (1.0 - e_j))
    delta = v * g_j * (score - e_j)

    # Passo 5: nuova volatilità (algoritmo di Illinois).
    a = math.log(sigma * sigma)

    def f(x: float) -> float:
        ex = math.exp(x)
        num = ex * (delta * delta - phi * phi - v - ex)
        den = 2.0 * (phi * phi + v + ex) ** 2
        return num / den - (x - a) / (TAU * TAU)

    big_a = a
    if delta * delta > phi * phi + v:
        big_b = math.log(delta * delta - phi * phi - v)
    else:
        k = 1
        while f(a - k * TAU) < 0:
            k += 1
        big_b = a - k * TAU
    f_a, f_b = f(big_a), f(big_b)
    while abs(big_b - big_a) > EPSILON:
        big_c = big_a + (big_a - big_b) * f_a / (f_b - f_a)
        f_c = f(big_c)
        if f_c * f_b <= 0:
            big_a, f_a = big_b, f_b
        else:
            f_a /= 2.0
        big_b, f_b = big_c, f_c
    new_sigma = math.exp(big_a / 2.0)

    phi_star = math.sqrt(phi * phi + new_sigma * new_sigma)
    new_phi = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    new_mu = mu + new_phi * new_phi * g_j * (score - e_j)

    new_rd = min(MAX_RD, max(MIN_RD, new_phi * SCALE))
    return Rating(rating=new_mu * SCALE + 1500.0, rd=new_rd, volatility=new_sigma)
