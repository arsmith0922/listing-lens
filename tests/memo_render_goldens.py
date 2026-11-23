"""The plain-text projections of run 2's nine drafts (D71), pinned: draft name, the SHA-256 of the
projection, its lines and its characters. The sentences in them are checked by hand elsewhere (the
fill, rules and sources tests); these catch any change to the whole."""

from __future__ import annotations

GOLDENS = (
    ("aacg.one", "393547b25926180fbb21a88568b3a6139d1f4093a839c1f4267b27bd554fb490", 130, 10888),
    ("agmh.one", "3f46cda4b8b893f88771a69e59260faca074d7781321509c76fbcaa4a4ee35cd", 128, 10763),
    ("aixi.one", "0938b0e5691731d8588a205ef9892dc7c87ac5913ceb37c6c68be2c2ced3c3ac", 150, 12806),
    (
        "credit_suisse.one",
        "493b861e680c038eda3875f945ada93fd4dc0c86559fdf7258a65828817f3713",
        135,
        10536,
    ),
    ("ge.one", "0f5fe819de44755839f40ef6d674dd64cf73df311b2ae829843333a565be7df9", 127, 10088),
    ("luckin.one", "87ad875cb8ce1c49d58ea0fe38021f71c5751802da8ffc92f4df27eaac8b9eef", 139, 11715),
    (
        "trans_american.one",
        "94d14a9c0007cd133de7ff208c426583837bf62c87f4ba7872737c38e5d5d8fc",
        141,
        11905,
    ),
    ("aixi.three", "de84497ef74dfd1e5712c82212285c9789b00fc5a509a28692a9bde146eee227", 269, 27139),
    (
        "trans_american.three",
        "1fff352d3b1b352d6b206a6f9bd058e357c19e622baef87e2645b19bd051d9b8",
        259,
        24992,
    ),
)
