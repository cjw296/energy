from functools import partial

import pook
from testfixtures import compare as compare_

from octopus import OctopusRESTClient

compare = partial(compare_, strict=True)


def test_gsp():
    with pook.use():
        (pook.get('https://api.octopus.energy/v1/electricity-meter-points/1000000000000/')
         .header('Authorization', 'Basic a2V5Og==')
         .reply(200).json({'gsp': '_C', 'mpan': '1000000000000', 'profile_class': 1}))
        compare(OctopusRESTClient('key').gsp('1000000000000'), expected='_C')
        compare(pook.isdone(), expected=True)
