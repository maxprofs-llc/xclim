# -*- coding: utf-8 -*-

"""
Indices library
===============

This module describes climate indicator functions. Functions are listed in alphabetical order and describe the raw
computation performed over xarray.DataArrays. DataArrays should carry unit information to allow for any needed
unit conversions. The output's attributes (CF-Convention) are not modified. Validation checks and output attributes
are handled by indicator classes described in files named by the physical variable (temperature, precip, streamflow).

Notes for docstring
-------------------

The docstrings adhere to the `NumPy`_ style convention and is meant as a way to store CF-Convention metadata as
well as information relevant to third party libraries (such as a WPS server).

The first line of the docstring (the short summary), will be assigned to the output's `long_name` attribute. The
`long_name` attribute is defined by the NetCDF User Guide to contain a long descriptive name which may, for example,
be used for labeling plots

The second paragraph will be considered as the "*abstract*", or the CF global "*comment*" (miscellaneous information
about the data or methods used to produce it).

The third and fourth sections are the **Parameters** and **Returns** sections describing the input and output values
respectively.

.. code-block:: python

   Parameters
   ----------
   <standard_name> : xarray.DataArray
     <Long_name> of variable [acceptable units].
   threshold : string
     Description of the threshold / units.
     e.g. The 10th percentile of historical temperature [K].
   freq : str, optional
     Resampling frequency.

   Returns
   -------
   xarray.DataArray
     Output's <long_name> [units]

The next sections would be **Notes** and **References**:

.. code-block:: python

    Notes
    -----
    This is where the mathematical equation is described.
    At the end of the description, convention suggests
    to add a reference [example]_:

        .. math::

            3987^12 + 4365^12 = 4472^12

    References
    ----------
    .. [example] Smith, T.J. and Huard, D. (2018). "CF Docstrings:
        A manifesto on conventions and the metaphysical nature
        of ontological python documentation." Climate Aesthetics,
        vol. 1, pp. 121-155.

Indice descriptions
===================
.. _`NumPy`: https://numpydoc.readthedocs.io/en/latest/format.html#docstring-standard
"""
import logging
import numpy as np
from xclim import utils
import xarray as xr
from xclim import run_length as rl
from xclim.utils import units, declare_units

logging.basicConfig(level=logging.DEBUG)
logging.captureWarnings(True)

xr.set_options(enable_cftimeindex=True)  # Set xarray to use cftimeindex

# if six.PY2:
#     from funcsigs import signature
# elif six.PY3:
#     from inspect import signature


# Frequencies : YS: year start, QS-DEC: seasons starting in december, MS: month start
# See http://pandas.pydata.org/pandas-docs/stable/timeseries.html#offset-aliases


# TODO: Define a unit conversion system for temperature [K, C, F] and precipitation [mm h-1, Kg m-2 s-1] metrics
# TODO: Move utility functions to another file.
# TODO: Should we reference the standard vocabulary we're using ?
# E.g. http://vocab.nerc.ac.uk/collection/P07/current/BHMHISG2/


# -------------------------------------------------- #
# ATTENTION: ASSUME ALL INDICES WRONG UNTIL TESTED ! #
# -------------------------------------------------- #

@declare_units('', q='[discharge]')
def base_flow_index(q, freq='YS'):
    r"""Base flow index

    Return the base flow index, defined as the minimum 7-day average flow divided by the mean flow.

    Parameters
    ----------
    q : xarray.DataArray
      Rate of river discharge [m³/s]
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArrray
      Base flow index.

    Notes
    -----
    Let :math:`\mathbf{q}=q_0, q_1, \ldots, q_n` be the sequence of daily discharge and :math:`\overline{\mathbf{q}}`
    the mean flow over the period. The base flow index is given by:

    .. math::

       \frac{\min(\mathrm{CMA}_7(\mathbf{q}))}{\overline{\mathbf{q}}}


    where :math:`\mathrm{CMA}_7` is the seven days moving average of the daily flow:

    .. math::

       \mathrm{CMA}_7(q_i) = \frac{\sum_{j=i-3}^{i+3} q_j}{7}

    """

    m7 = q.rolling(time=7, center=True).mean().resample(time=freq)
    mq = q.resample(time=freq)

    m7m = m7.min(dim='time')
    return m7m / mq.mean(dim='time')


@declare_units('days', tasmin='[temperature]', tn10='[temperature]')
def cold_spell_duration_index(tasmin, tn10, window=6, freq='YS'):
    r"""Cold spell duration index

    Number of days with at least six consecutive days where the daily minimum temperature is below the 10th
    percentile.

    Parameters
    ----------
    tasmin : xarray.DataArray
      Minimum daily temperature.
    tn10 : float
      10th percentile of daily minimum temperature.
    window : int
      Minimum number of days with temperature below threshold to qualify as a cold spell. Default: 6.
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      Count of days with at least six consecutive days where the daily minimum temperature is below the 10th
      percentile [days].

    Notes
    -----
    Let :math:`TN_i` be the minimum daily temperature for the day of the year :math:`i` and :math:`TN10_i` the 10th
    percentile of the minimum daily temperature over the 1961-1990 period for day of the year :math:`i`, the cold spell
    duration index over period :math:`\phi` is defined as:

    .. math::

       \sum_{i \in \phi} \prod_{j=i}^{i+6} \left[ TN_j < TN10_j \right]

    where :math:`[P]` is 1 if :math:`P` is true, and 0 if false.

    References
    ----------
    From the Expert Team on Climate Change Detection, Monitoring and Indices (ETCCDMI).

    Example
    -------
    >>> tn10 = percentile_doy(historical_tasmin, per=.1)
    >>> cold_spell_duration_index(reference_tasmin, tn10)
    """
    if 'dayofyear' not in tn10.coords.keys():
        raise AttributeError("tn10 should have dayofyear coordinates.")

    # The day of year value of the tasmin series.
    doy = tasmin.indexes['time'].dayofyear

    tn10 = utils.convert_units_to(tn10, tasmin)
    # If calendar of `tn10` is different from `tasmin`, interpolate.
    tn10 = utils.adjust_doy_calendar(tn10, tasmin)

    # Create an array with the shape and coords of tasmin, but with values set to tx90 according to the doy index.
    thresh = xr.full_like(tasmin, np.nan)
    thresh.data = tn10.sel(dayofyear=doy)

    below = (tasmin < thresh)

    return below.resample(time=freq).apply(rl.windowed_run_count, window=window, dim='time')


def cold_and_dry_days(tas, tgin25, pr, wet25, freq='YS'):
    r"""Cold and dry days.

    Returns the total number of days where "Cold" and "Dry" conditions coincide.

    Parameters
    ----------
    tas : xarray.DataArray
      Mean daily temperature values [℃] or [K]
    tgin25 : xarray.DataArray
      First quartile of daily mean temperature computed by month.
    pr : xarray.DataArray
      Daily precipitation.
    wet25 : xarray.DataArray
      First quartile of daily total precipitation computed by month.
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      The total number of days where cold and dry conditions coincide.

    Notes
    -----
    Formula to be written [cold_dry_days]_.

    References
    ----------
    .. [cold_dry_days] Beniston, M. (2009). Trends in joint quantiles of temperature and precipitation in Europe
        since 1901 and projected for 2100. Geophysical Research Letters, 36(7). https://doi.org/10.1029/2008GL037119
    """
    raise NotImplementedError
    # There is an issue with the 1 mm threshold. It makes no sense to assume a day with < 1mm is not dry.
    # c1 = tas < utils.convert_units_to(tgin25, tas)
    # c2 = (pr > utils.convert_units_to('1 mm', pr)) * (pr < utils.convert_units_to(wet25, pr))

    # c = (c1 * c2) * 1
    # return c.resample(time=freq).sum(dim='time')


@declare_units('days', pr='[precipitation]', thresh='[precipitation]')
def maximum_consecutive_dry_days(pr, thresh='1 mm/day', freq='YS'):
    r"""Maximum number of consecutive dry days

    Return the maximum number of consecutive days within the period where precipitation
    is below a certain threshold.

    Parameters
    ----------
    pr : xarray.DataArray
      Mean daily precipitation flux [mm]
    thresh : str
      Threshold precipitation on which to base evaluation [mm]. Default : '1 mm/day'
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      The maximum number of consecutive dry days.

    Notes
    -----
    Let :math:`\mathbf{p}=p_0, p_1, \ldots, p_n` be a daily precipitation series and :math:`thresh` the threshold
    under which a day is considered dry. Then let :math:`\mathbf{s}` be the sorted vector of indices :math:`i` where
    :math:`[p_i < thresh] \neq [p_{i+1} < thresh]`, that is, the days when the temperature crosses the threshold.
    Then the maximum number of consecutive dry days is given by

    .. math::

       \max(\mathbf{d}) \quad \mathrm{where} \quad d_j = (s_j - s_{j-1}) [p_{s_j} > thresh]

    where :math:`[P]` is 1 if :math:`P` is true, and 0 if false. Note that this formula does not handle sequences at
    the start and end of the series, but the numerical algorithm does.
    """
    t = utils.convert_units_to(thresh, pr, 'hydro')
    group = (pr < t).resample(time=freq)

    return group.apply(rl.longest_run, dim='time')


@declare_units('days', tasmin='[temperature]')
def consecutive_frost_days(tasmin, freq='AS-JUL'):
    r"""Maximum number of consecutive frost days (Tmin < 0℃).

    Resample the daily minimum temperature series by computing the maximum number
    of days below the freezing point over each period.

    Parameters
    ----------
    tasmin : xarray.DataArray
      Minimum daily temperature values [℃] or [K]
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      The maximum number of consecutive days below the freezing point.

    Notes
    -----
    Let :math:`\mathbf{x}=x_0, x_1, \ldots, x_n` be a daily minimum temperature series and
    :math:`\mathbf{s}` be the sorted vector of indices :math:`i` where :math:`[p_i < 0\celsius] \neq [p_{i+1} <
    0\celsius]`, that is, the days when the temperature crosses the freezing point.
    Then the maximum number of consecutive frost days is given by

    .. math::

       \max(\mathbf{d}) \quad \mathrm{where} \quad d_j = (s_j - s_{j-1}) [x_{s_j} > 0\celsius]

    where :math:`[P]` is 1 if :math:`P` is true, and 0 if false. Note that this formula does not handle sequences at
    the start and end of the series, but the numerical algorithm does.
    """
    tu = units.parse_units(tasmin.attrs['units'].replace('-', '**-'))
    fu = 'degC'
    frz = 0
    if fu != tu:
        frz = units.convert(frz, fu, tu)
    group = (tasmin < frz).resample(time=freq)
    return group.apply(rl.longest_run, dim='time')


@declare_units('days', tasmax='[temperature]', tasmin='[temperature]')
def daily_freezethaw_cycles(tasmax, tasmin, freq='YS'):
    r"""Number of days with a diurnal freeze-thaw cycle

    The number of days where Tmax > 0℃ and Tmin < 0℃.

    Parameters
    ----------
    tasmax : xarray.DataArray
      Maximum daily temperature [℃] or [K]
    tasmin : xarray.DataArray
      Minimum daily temperature values [℃] or [K]
    freq : str
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      Number of days with a diurnal freeze-thaw cycle

    Notes
    -----
    Let :math:`TX_{i}` be the maximum temperature at day :math:`i` and :math:`TN_{i}` be
    the daily minimum temperature at day :math:`i`. Then the number of freeze thaw cycles
    during period :math:`\phi` is given by :

    .. math::

        \sum_{i \in \phi} [ TX_{i} > 0℃ ] [ TN_{i} <  0℃ ]

    where :math:`[P]` is 1 if :math:`P` is true, and 0 if false.
    """
    frz = utils.convert_units_to('0 degC', tasmax)
    ft = (tasmin < frz) * (tasmax > frz) * 1
    out = ft.resample(time=freq).sum(dim='time')
    return out


@declare_units('K', tasmax='[temperature]', tasmin='[temperature]')
def daily_temperature_range(tasmax, tasmin, freq='YS'):
    r"""Mean of daily temperature range.

    The mean difference between the daily maximum temperature and the daily minimum temperature.

    Parameters
    ----------
    tasmax : xarray.DataArray
      Maximum daily temperature values [℃] or [K]
    tasmin : xarray.DataArray
      Minimum daily temperature values [℃] or [K]
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      The average variation in daily temperature range for the given time period.

    Notes
    -----
    Let :math:`TX_{ij}` and :math:`TN_{ij}` be the daily maximum and minimum temperature at day :math:`i`
    of period :math:`j`. Then the mean diurnal temperature range in period :math:`j` is:

    .. math::

        DTR_j = \frac{ \sum_{i=1}^I (TX_{ij} - TN_{ij}) }{I}
    """

    dtr = tasmax - tasmin
    out = dtr.resample(time=freq).mean(dim='time', keep_attrs=True)
    out.attrs['units'] = tasmax.units
    return out


# TODO: Improve description.
@declare_units('K', tasmax='[temperature]', tasmin='[temperature]')
def daily_temperature_range_variability(tasmax, tasmin, freq="YS"):
    r"""Mean absolute day-to-day variation in daily temperature range.

    Mean absolute day-to-day variation in daily temperature range.

    Parameters
    ----------
    tasmax : xarray.DataArray
      Maximum daily temperature values [℃] or [K]
    tasmin : xarray.DataArray
      Minimum daily temperature values [℃] or [K]
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      The average day-to-day variation in daily temperature range for the given time period.

    Notes
    -----
    Let :math:`TX_{ij}` and :math:`TN_{ij}` be the daily maximum and minimum temperature at
    day :math:`i` of period :math:`j`. Then calculated is the absolute day-to-day differences in
    period :math:`j` is:

    .. math::

       vDTR_j = \frac{ \sum_{i=2}^{I} |(TX_{ij}-TN_{ij})-(TX_{i-1,j}-TN_{i-1,j})| }{I}
    """

    vdtr = abs((tasmax - tasmin).diff(dim='time'))
    out = vdtr.resample(time=freq).mean(dim='time')
    out.attrs['units'] = tasmax.units
    return out


@declare_units('K', tasmax='[temperature]', tasmin='[temperature]')
def extreme_temperature_range(tasmax, tasmin, freq='YS'):
    r"""Extreme intra-period temperature range.

    The maximum of max temperature (TXx) minus the minimum of min temperature (TNn) for the given time period.

    Parameters
    ----------
    tasmax : xarray.DataArray
      Maximum daily temperature values [℃] or [K]
    tasmin : xarray.DataArray
      Minimum daily temperature values [℃] or [K]
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      Extreme intra-period temperature range for the given time period.

    Notes
    -----
    Let :math:`TX_{ij}` and :math:`TN_{ij}` be the daily maximum and minimum temperature at day :math:`i`
    of period :math:`j`. Then the extreme temperature range in period :math:`j` is:

    .. math::

        ETR_j = max(TX_{ij}) - min(TN_{ij})
    """

    tx_max = tasmax.resample(time=freq).max(dim='time')
    tn_min = tasmin.resample(time=freq).min(dim='time')

    out = tx_max - tn_min
    out.attrs['units'] = tasmax.units
    return out


@declare_units('days', tasmin='[temperature]')
def frost_days(tasmin, freq='YS'):
    r"""Frost days index

    Number of days where daily minimum temperatures are below 0℃.

    Parameters
    ----------
    tasmin : xarray.DataArray
      Minimum daily temperature [℃] or [K]
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      Frost days index.

    Notes
    -----
    Let :math:`TN_{ij}` be the daily minimum temperature at day :math:`i` of period :math:`j`. Then
    counted is the number of days where:

    .. math::

        TN_{ij} < 0℃
    """
    tu = units.parse_units(tasmin.attrs['units'].replace('-', '**-'))
    fu = 'degC'
    frz = 0
    if fu != tu:
        frz = units.convert(frz, fu, tu)
    f = (tasmin < frz) * 1
    return f.resample(time=freq).sum(dim='time')


@declare_units('', tasmin='[temperature]', tasmax='[temperature]', thresh_tasmin='[temperature]',
               thresh_tasmax='[temperature]')
def heat_wave_frequency(tasmin, tasmax, thresh_tasmin='22.0 degC', thresh_tasmax='30 degC',
                        window=3, freq='YS'):
    # Dev note : we should decide if it is deg K or C
    r"""Heat wave frequency

    Number of heat waves over a given period. A heat wave is defined as an event
    where the minimum and maximum daily temperature both exceeds specific thresholds
    over a minimum number of days.

    Parameters
    ----------

    tasmin : xarrray.DataArray
      Minimum daily temperature [℃] or [K]
    tasmax : xarrray.DataArray
      Maximum daily temperature [℃] or [K]
    thresh_tasmin : str
      The minimum temperature threshold needed to trigger a heatwave event [℃] or [K]. Default : '22 degC'
    thresh_tasmax : str
      The maximum temperature threshold needed to trigger a heatwave event [℃] or [K]. Default : '30 degC'
    window : int
      Minimum number of days with temperatures above thresholds to qualify as a heatwave.
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      Number of heatwave at the wanted frequency

    Notes
    -----
    The thresholds of 22° and 25°C for night temperatures and 30° and 35°C for day temperatures were selected by
    Health Canada professionals, following a temperature–mortality analysis. These absolute temperature thresholds
    characterize the occurrence of hot weather events that can result in adverse health outcomes for Canadian
    communities (Casati et al., 2013).

    In Robinson (2001), the parameters would be `thresh_tasmin=27.22, thresh_tasmax=39.44, window=2` (81F, 103F).

    References
    ----------
    Casati, B., A. Yagouti, and D. Chaumont, 2013: Regional Climate Projections of Extreme Heat Events in Nine Pilot
    Canadian Communities for Public Health Planning. J. Appl. Meteor. Climatol., 52, 2669–2698,
    https://doi.org/10.1175/JAMC-D-12-0341.1

    Robinson, P.J., 2001: On the Definition of a Heat Wave. J. Appl. Meteor., 40, 762–775,
    https://doi.org/10.1175/1520-0450(2001)040<0762:OTDOAH>2.0.CO;2
    """
    thresh_tasmax = utils.convert_units_to(thresh_tasmax, tasmax)
    thresh_tasmin = utils.convert_units_to(thresh_tasmin, tasmin)

    cond = (tasmin > thresh_tasmin) & (tasmax > thresh_tasmax)
    group = cond.resample(time=freq)
    return group.apply(rl.windowed_run_events, window=window, dim='time')


@declare_units('days', tasmin='[temperature]', tasmax='[temperature]', thresh_tasmin='[temperature]',
               thresh_tasmax='[temperature]')
def heat_wave_max_length(tasmin, tasmax, thresh_tasmin='22.0 degC', thresh_tasmax='30 degC',
                         window=3, freq='YS'):
    # Dev note : we should decide if it is deg K or C
    r"""Heat wave max length

    Maximum length of heat waves over a given period. A heat wave is defined as an event
    where the minimum and maximum daily temperature both exceeds specific thresholds
    over a minimum number of days.

    By definition heat_wave_max_length must be >= window.

    Parameters
    ----------

    tasmin : xarrray.DataArray
      Minimum daily temperature [℃] or [K]
    tasmax : xarrray.DataArray
      Maximum daily temperature [℃] or [K]
    thresh_tasmin : str
      The minimum temperature threshold needed to trigger a heatwave event [℃] or [K]. Default : '22 degC'
    thresh_tasmax : str
      The maximum temperature threshold needed to trigger a heatwave event [℃] or [K]. Default : '30 degC'
    window : int
      Minimum number of days with temperatures above thresholds to qualify as a heatwave.
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      Maximum length of heatwave at the wanted frequency

    Notes
    -----
    The thresholds of 22° and 25°C for night temperatures and 30° and 35°C for day temperatures were selected by
    Health Canada professionals, following a temperature–mortality analysis. These absolute temperature thresholds
    characterize the occurrence of hot weather events that can result in adverse health outcomes for Canadian
    communities (Casati et al., 2013).

    In Robinson (2001), the parameters would be `thresh_tasmin=27.22, thresh_tasmax=39.44, window=2` (81F, 103F).

    References
    ----------
    Casati, B., A. Yagouti, and D. Chaumont, 2013: Regional Climate Projections of Extreme Heat Events in Nine Pilot
    Canadian Communities for Public Health Planning. J. Appl. Meteor. Climatol., 52, 2669–2698,
    https://doi.org/10.1175/JAMC-D-12-0341.1

    Robinson, P.J., 2001: On the Definition of a Heat Wave. J. Appl. Meteor., 40, 762–775,
    https://doi.org/10.1175/1520-0450(2001)040<0762:OTDOAH>2.0.CO;2
    """
    thresh_tasmax = utils.convert_units_to(thresh_tasmax, tasmax)
    thresh_tasmin = utils.convert_units_to(thresh_tasmin, tasmin)

    cond = (tasmin > thresh_tasmin) & (tasmax > thresh_tasmax)
    group = cond.resample(time=freq)
    max_l = group.apply(rl.longest_run, dim='time')
    return max_l.where(max_l >= window, 0)


@declare_units('days', tasmax='[temperature]')
def ice_days(tasmax, freq='YS'):
    r"""Number of ice/freezing days

    Number of days where daily maximum temperatures are below 0℃.

    Parameters
    ----------
    tasmax : xarrray.DataArray
      Maximum daily temperature [℃] or [K]
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      Number of ice/freezing days.

    Notes
    -----
    Let :math:`TX_{ij}` be the daily maximum temperature at day :math:`i` of period :math:`j`. Then
    counted is the number of days where:

    .. math::

        TX_{ij} < 0℃
    """
    tu = units.parse_units(tasmax.attrs['units'].replace('-', '**-'))
    fu = 'degC'
    frz = 0
    if fu != tu:
        frz = units.convert(frz, fu, tu)
    f = (tasmax < frz) * 1
    return f.resample(time=freq).sum(dim='time')


@declare_units('', pr='[precipitation]', prsn='[precipitation]', tas='[temperature]')
def liquid_precip_ratio(pr, prsn=None, tas=None, freq='QS-DEC'):
    r"""Ratio of rainfall to total precipitation

    The ratio of total liquid precipitation over the total precipitation. If solid precipitation is not provided,
    then precipitation is assumed solid if the temperature is below 0°C.

    Parameters
    ----------
    pr : xarray.DataArray
      Mean daily precipitation flux [Kg m-2 s-1] or [mm].
    prsn : xarray.DataArray
      Mean daily solid precipitation flux [Kg m-2 s-1] or [mm].
    tas : xarray.DataArray
      Mean daily temperature [℃] or [K]
    freq : str
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      Ratio of rainfall to total precipitation

    Notes
    -----
    Let :math:`PR_i` be the mean daily precipitation of day :math:`i`, then for a period :math:`j` starting at
    day :math:`a` and finishing on day :math:`b`:

    .. math::

        PR_{ij} = \sum_{i=a}^{b} PR_i


        PRwet_{ij}

    See also
    --------
    winter_rain_ratio
    """

    if prsn is None:
        tu = units.parse_units(tas.attrs['units'].replace('-', '**-'))
        fu = 'degC'
        frz = 0
        if fu != tu:
            frz = units.convert(frz, fu, tu)
        prsn = pr.where(tas < frz, 0)

    tot = pr.resample(time=freq).sum(dim='time')
    rain = tot - prsn.resample(time=freq).sum(dim='time')
    ratio = rain / tot
    return ratio


@declare_units('mm', pr='[precipitation]')
def max_n_day_precipitation_amount(pr, window=1, freq='YS'):
    r"""Highest precipitation amount cumulated over a n-day moving window.

    Calculate the n-day rolling sum of the original daily total precipitation series
    and determine the maximum value over each period.

    Parameters
    ----------
    da : xarray.DataArray
      Daily precipitation values [Kg m-2 s-1] or [mm]
    window : int
      Window size in days.
    freq : str, optional
      Resampling frequency : default 'YS' (yearly)

    Returns
    -------
    xarray.DataArray
      The highest cumulated n-day precipitation value at the given time frequency.

    Examples
    --------
    The following would compute for each grid cell of file `pr.day.nc` the highest 5-day total precipitation
    at an annual frequency:

    >>> da = xr.open_dataset('pr.day.nc').pr
    >>> window = 5
    >>> output = max_n_day_precipitation_amount(da, window, freq="YS")
    """

    # rolling sum of the values
    arr = pr.rolling(time=window, center=False).sum()
    out = arr.resample(time=freq).max(dim='time', keep_attrs=True)

    out.attrs['units'] = pr.units
    # Adjust values and units to make sure they are daily
    return utils.pint_multiply(out, 1 * units.day, 'mm')


@declare_units('mm/day', pr='[precipitation]')
def max_1day_precipitation_amount(pr, freq='YS'):
    r"""Highest 1-day precipitation amount for a period (frequency).

    Resample the original daily total precipitation temperature series by taking the max over each period.

    Parameters
    ----------
    pr : xarray.DataArray
      Daily precipitation values [Kg m-2 s-1] or [mm]
    freq : str, optional
      Resampling frequency one of : 'YS' (yearly) ,'M' (monthly), or 'QS-DEC' (seasonal - quarters starting in december)

    Returns
    -------
    xarray.DataArray
      The highest 1-day precipitation value at the given time frequency.

    Notes
    -----
    Let :math:`PR_i` be the mean daily precipitation of day `i`, then for a period `j`:

    .. math::

       PRx_{ij} = max(PR_{ij})

    Examples
    --------
    The following would compute for each grid cell of file `pr.day.nc` the highest 1-day total
    at an annual frequency:

    >>> pr = xr.open_dataset('pr.day.nc').pr
    >>> rx1day = max_1day_precipitation_amount(pr, freq="YS")
    """

    out = pr.resample(time=freq).max(dim='time', keep_attrs=True)
    return utils.convert_units_to(out, 'mm/day', 'hydro')


@declare_units('mm', pr='[precipitation]')
def precip_accumulation(pr, freq='YS'):
    r"""Accumulated total (liquid + solid) precipitation.

    Resample the original daily mean precipitation flux and accumulate over each period.

    Parameters
    ----------
    pr : xarray.DataArray
      Mean daily precipitation flux [Kg m-2 s-1] or [mm].
    freq : str, optional
      Resampling frequency as defined in
      http://pandas.pydata.org/pandas-docs/stable/timeseries.html#resampling.

    Returns
    -------
    xarray.DataArray
      The total daily precipitation at the given time frequency.

    Notes
    -----
    Let :math:`PR_i` be the mean daily precipitation of day :math:`i`, then for a period :math:`j` starting at
    day :math:`a` and finishing on day :math:`b`:

    .. math::

       PR_{ij} = \sum_{i=a}^{b} PR_i

    Examples
    --------
    The following would compute for each grid cell of file `pr_day.nc` the total
    precipitation at the seasonal frequency, ie DJF, MAM, JJA, SON, DJF, etc.:

    >>> pr_day = xr.open_dataset('pr_day.nc').pr
    >>> prcp_tot_seasonal = precip_accumulation(pr_day, freq="QS-DEC")
    """

    out = pr.resample(time=freq).sum(dim='time', keep_attrs=True)
    return utils.pint_multiply(out, 1 * units.day, 'mm')


@declare_units('days', pr='[precipitation]', tas='[temperature]', thresh='[precipitation]')
def rain_on_frozen_ground_days(pr, tas, thresh='1 mm/d', freq='YS'):
    """Number of rain on frozen ground events

    Number of days with rain above a threshold after a series of seven days below freezing temperature.
    Precipitation is assumed to be rain when the temperature is above 0℃.

    Parameters
    ----------
    pr : xarray.DataArray
      Mean daily precipitation flux [Kg m-2 s-1] or [mm]
    tas : xarray.DataArray
      Mean daily temperature [℃] or [K]
    thresh : str
      Precipitation threshold to consider a day as a rain event. Default : '1 mm/d'
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      The number of rain on frozen ground events per period [days]

    Notes
    -----
    Let :math:`PR_i` be the mean daily precipitation and :math:`TG_i` be the mean daily temperature of day :math:`i`.
    Then for a period :math:`j`, rain on frozen grounds days are counted where:

    .. math::

        PR_{i} > Threshold [mm]

    and where

    .. math::

        TG_{i} ≤ 0℃

    is true for continuous periods where :math:`i ≥ 7`

    """
    t = utils.convert_units_to(thresh, pr)
    frz = utils.convert_units_to('0 C', tas)

    def func(x, axis):
        """Check that temperature conditions are below 0 for seven days and above after."""
        frozen = x == np.array([0, 0, 0, 0, 0, 0, 0, 1], bool)
        return frozen.all(axis=axis)

    tcond = (tas > frz).rolling(time=8).reduce(func)
    pcond = (pr > t)

    return (tcond * pcond * 1).resample(time=freq).sum(dim='time')


# TODO: Improve description
@declare_units('days', tas='[temperature]', t90='[temperature]')
def tg90p(tas, t90, freq='YS'):
    r"""Number of days with daily mean temperature over the 90th percentile.

    Number of days with daily mean temperature over the 90th percentile.

    Parameters
    ----------
    tas : xarray.DataArray
      Mean daily temperature [℃] or [K]
    t90 : xarray.DataArray
      90th percentile of daily mean temperature [℃] or [K]
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      Count of days with daily mean temperature below the 10th percentile [days]

    Notes
    -----
    The 90th percentile should be computed for a 5 day window centered on each calendar day for a reference period.

    Example
    -------
    >>> t90 = percentile_doy(historical_tas, per=0.9)
    >>> hot_days = tg90p(tas, t90)
    """
    if 'dayofyear' not in t90.coords.keys():
        raise AttributeError("t10 should have dayofyear coordinates.")

    t90 = utils.convert_units_to(t90, tas)

    # adjustment of t90 to tas doy range
    t90 = utils.adjust_doy_calendar(t90, tas)

    # create array of percentile with tas shape and coords
    thresh = xr.full_like(tas, np.nan)
    doy = thresh.time.dt.dayofyear.values
    thresh.data = t90.sel(dayofyear=doy)

    # compute the cold days
    over = (tas > thresh)

    return over.resample(time=freq).sum(dim='time')


# TODO: Improve description
@declare_units('days', tas='[temperature]', t10='[temperature]')
def tg10p(tas, t10, freq='YS'):
    r"""Number of days with daily mean temperature below the 10th percentile.

    Number of days with daily mean temperature below the 10th percentile.

    Parameters
    ----------
    tas : xarray.DataArray
      Mean daily temperature [℃] or [K]
    t10 : xarray.DataArray
      10th percentile of daily mean temperature [℃] or [K]
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      Count of days with daily mean temperature below the 10th percentile [days]

    Notes
    -----
    The 10th percentile should be computed for a 5 day window centered on each calendar day for a reference period.

    Example
    -------
    >>> t10 = percentile_doy(historical_tas, per=0.1)
    >>> cold_days = tg10p(tas, t10)
    """
    if 'dayofyear' not in t10.coords.keys():
        raise AttributeError("t10 should have dayofyear coordinates.")

    t10 = utils.convert_units_to(t10, tas)

    # adjustment of t10 to tas doy range
    t10 = utils.adjust_doy_calendar(t10, tas)

    # create array of percentile with tas shape and coords
    thresh = xr.full_like(tas, np.nan)
    doy = thresh.time.dt.dayofyear.values
    thresh.data = t10.sel(dayofyear=doy)

    # compute the cold days
    below = (tas < thresh)

    return below.resample(time=freq).sum(dim='time')


# TODO: Improve description
@declare_units('days', tasmin='[temperature]', t90='[temperature]')
def tn90p(tasmin, t90, freq='YS'):
    r"""Number of days with daily minimum temperature over the 90th percentile.

    Number of days with daily minimum temperature over the 90th percentile.

    Parameters
    ----------
    tasmin : xarray.DataArray
      Minimum daily temperature [℃] or [K]
    t90 : xarray.DataArray
      90th percentile of daily minimum temperature [℃] or [K]
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      Count of days with daily minimum temperature below the 10th percentile [days]

    Notes
    -----
    The 90th percentile should be computed for a 5 day window centered on each calendar day for a reference period.

    Example
    -------
    >>> t90 = percentile_doy(historical_tas, per=0.9)
    >>> hot_days = tg90p(tas, t90)
    """
    if 'dayofyear' not in t90.coords.keys():
        raise AttributeError("t10 should have dayofyear coordinates.")
    t90 = utils.convert_units_to(t90, tasmin)
    # adjustment of t90 to tas doy range
    t90 = utils.adjust_doy_calendar(t90, tasmin)

    # create array of percentile with tas shape and coords
    thresh = xr.full_like(tasmin, np.nan)
    doy = thresh.time.dt.dayofyear.values
    thresh.data = t90.sel(dayofyear=doy)

    # compute the cold days
    over = (tasmin > thresh)

    return over.resample(time=freq).sum(dim='time')


# TODO: Improve description
@declare_units('days', tasmin='[temperature]', t10='[temperature]')
def tn10p(tasmin, t10, freq='YS'):
    r"""Number of days with daily minimum temperature below the 10th percentile.

    Number of days with daily minimum temperature below the 10th percentile.

    Parameters
    ----------

    tasmin : xarray.DataArray
      Mean daily temperature [℃] or [K]
    t10 : xarray.DataArray
      10th percentile of daily minimum temperature [℃] or [K]
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      Count of days with daily minimum temperature below the 10th percentile [days]

    Notes
    -----
    The 10th percentile should be computed for a 5 day window centered on each calendar day for a reference period.

    Example
    -------
    >>> t10 = percentile_doy(historical_tas, per=0.1)
    >>> cold_days = tg10p(tas, t10)
    """
    if 'dayofyear' not in t10.coords.keys():
        raise AttributeError("t10 should have dayofyear coordinates.")
    t10 = utils.convert_units_to(t10, tasmin)

    # adjustment of t10 to tas doy range
    t10 = utils.adjust_doy_calendar(t10, tasmin)

    # create array of percentile with tas shape and coords
    thresh = xr.full_like(tasmin, np.nan)
    doy = thresh.time.dt.dayofyear.values
    thresh.data = t10.sel(dayofyear=doy)

    # compute the cold days
    below = (tasmin < thresh)

    return below.resample(time=freq).sum(dim='time')


@declare_units('days', tasmin='[temperature]', thresh='[temperature]')
def tropical_nights(tasmin, thresh='20.0 degC', freq='YS'):
    r"""Tropical nights

    The number of days with minimum daily temperature above threshold.

    Parameters
    ----------
    tasmin : xarray.DataArray
      Minimum daily temperature [℃] or [K]
    thresh : str
      Threshold temperature on which to base evaluation [℃] or [K]. Default: '20 degC'.
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      Number of days with minimum daily temperature above threshold.

    Notes
    -----
    Let :math:`TN_{ij}` be the daily minimum temperature at day :math:`i` of period :math:`j`. Then
    counted is the number of days where:

    .. math::

        TN_{ij} > Threshold [℃]
    """
    thresh = utils.convert_units_to(thresh, tasmin)
    return tasmin.pipe(lambda x: (tasmin > thresh) * 1) \
        .resample(time=freq) \
        .sum(dim='time')


# TODO: Improve description
@declare_units('days', tasmax='[temperature]', t90='[temperature]')
def tx90p(tasmax, t90, freq='YS'):
    r"""Number of days with daily maximum temperature over the 90th percentile.

    Number of days with daily maximum temperature over the 90th percentile.

    Parameters
    ----------
    tasmax : xarray.DataArray
      Maximum daily temperature [℃] or [K]
    t90 : xarray.DataArray
      90th percentile of daily maximum temperature [℃] or [K]
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      Count of days with daily maximum temperature below the 10th percentile [days]

    Notes
    -----
    The 90th percentile should be computed for a 5 day window centered on each calendar day for a reference period.

    Example
    -------
    >>> t90 = percentile_doy(historical_tas, per=0.9)
    >>> hot_days = tg90p(tas, t90)
    """
    if 'dayofyear' not in t90.coords.keys():
        raise AttributeError("t10 should have dayofyear coordinates.")

    t90 = utils.convert_units_to(t90, tasmax)

    # adjustment of t90 to tas doy range
    t90 = utils.adjust_doy_calendar(t90, tasmax)

    # create array of percentile with tas shape and coords
    thresh = xr.full_like(tasmax, np.nan)
    doy = thresh.time.dt.dayofyear.values
    thresh.data = t90.sel(dayofyear=doy)

    # compute the cold days
    over = (tasmax > thresh)

    return over.resample(time=freq).sum(dim='time')


# TODO: Improve description
@declare_units('days', tasmax='[temperature]', t10='[temperature]')
def tx10p(tasmax, t10, freq='YS'):
    r"""Number of days with daily maximum temperature below the 10th percentile.

    Number of days with daily maximum temperature below the 10th percentile.

    Parameters
    ----------
    tasmax : xarray.DataArray
      Maximum daily temperature [℃] or [K]
    t10 : xarray.DataArray
      10th percentile of daily maximum temperature [℃] or [K]
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      Count of days with daily maximum temperature below the 10th percentile [days]

    Notes
    -----
    The 10th percentile should be computed for a 5 day window centered on each calendar day for a reference period.

    Example
    -------
    >>> t10 = percentile_doy(historical_tas, per=0.1)
    >>> cold_days = tg10p(tas, t10)
    """
    if 'dayofyear' not in t10.coords.keys():
        raise AttributeError("t10 should have dayofyear coordinates.")

    t10 = utils.convert_units_to(t10, tasmax)

    # adjustment of t10 to tas doy range
    t10 = utils.adjust_doy_calendar(t10, tasmax)

    # create array of percentile with tas shape and coords
    thresh = xr.full_like(tasmax, np.nan)
    doy = thresh.time.dt.dayofyear.values
    thresh.data = t10.sel(dayofyear=doy)

    # compute the cold days
    below = (tasmax < thresh)

    return below.resample(time=freq).sum(dim='time')


@declare_units('days', tasmin='[temperature]', tasmax='[temperature]', thresh_tasmin='[temperature]',
               thresh_tasmax='[temperature]')
def tx_tn_days_above(tasmin, tasmax, thresh_tasmin='22 degC',
                     thresh_tasmax='30 degC', freq='YS'):
    r"""Number of days with both hot maximum and minimum daily temperatures.

    The number of days per period with tasmin above a threshold and tasmax above another threshold.

    Parameters
    ----------
    tasmin : xarray.DataArray
      Minimum daily temperature [℃] or [K]
    tasmax : xarray.DataArray
      Maximum daily temperature [℃] or [K]
    thresh_tasmin : str
      Threshold temperature for tasmin on which to base evaluation [℃] or [K]. Default : '22 degC'
    thresh_tasmax : str
      Threshold temperature for tasmax on which to base evaluation [℃] or [K]. Default : '30 degC'
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      the number of days with tasmin > thresh_tasmin and
      tasmax > thresh_tasamax per period


    Notes
    -----
    Let :math:`TX_{ij}` be the maximum temperature at day :math:`i` of period :math:`j`, :math:`TN_{ij}`
    the daily minimum temperature at day :math:`i` of period :math:`j`, :math:`TX_{thresh}` the threshold for maximum
    daily temperature, and :math:`TN_{thresh}` the threshold for minimum daily temperature. Then counted is the number
    of days where:

    .. math::

        TX_{ij} > TX_{thresh} [℃]

    and where:

    .. math::

        TN_{ij} > TN_{thresh} [℃]

    """
    thresh_tasmax = utils.convert_units_to(thresh_tasmax, tasmax)
    thresh_tasmin = utils.convert_units_to(thresh_tasmin, tasmin)
    events = ((tasmin > (thresh_tasmin)) & (tasmax > (thresh_tasmax))) * 1
    return events.resample(time=freq).sum(dim='time')


@declare_units('days', tasmax='[temperature]', tx90='[temperature]')
def warm_spell_duration_index(tasmax, tx90, window=6, freq='YS'):
    r"""Warm spell duration index

    Number of days with at least six consecutive days where the daily maximum temperature is above the 90th
    percentile. The 90th percentile should be computed for a 5-day window centred on each calendar day in the
    1961-1990 period.

    Parameters
    ----------
    tasmax : xarray.DataArray
      Maximum daily temperature [℃] or [K]
    tx90 : float
      90th percentile of daily maximum temperature [℃] or [K]
    window : int
      Minimum number of days with temperature below threshold to qualify as a warm spell.
    freq : str, optional
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      Count of days with at least six consecutive days where the daily maximum temperature is above the 90th
      percentile [days].

    References
    ----------
    From the Expert Team on Climate Change Detection, Monitoring and Indices (ETCCDMI).
    Used in Alexander, L. V., et al. (2006), Global observed changes in daily climate extremes of temperature and
    precipitation, J. Geophys. Res., 111, D05109, doi: 10.1029/2005JD006290.

    """
    if 'dayofyear' not in tx90.coords.keys():
        raise AttributeError("tx90 should have dayofyear coordinates.")

    # The day of year value of the tasmax series.
    doy = tasmax.indexes['time'].dayofyear

    # adjustment of tx90 to tasmax doy range
    tx90 = utils.adjust_doy_calendar(tx90, tasmax)

    # Create an array with the shape and coords of tasmax, but with values set to tx90 according to the doy index.
    thresh = xr.full_like(tasmax, np.nan)
    thresh.data = tx90.sel(dayofyear=doy)

    above = (tasmax > thresh)

    return above.resample(time=freq).apply(rl.windowed_run_count, window=window, dim='time')


@declare_units('', pr='[precipitation]', prsn='[precipitation]', tas='[temperature]')
def winter_rain_ratio(pr, prsn=None, tas=None):
    """Ratio of rainfall to total precipitation during winter

    The ratio of total liquid precipitation over the total precipitation over the winter months (DJF. If solid
    precipitation is not provided, then precipitation is assumed solid if the temperature is below 0°C.

    Parameters
    ----------
    pr : xarray.DataArray
      Mean daily precipitation flux [Kg m-2 s-1] or [mm].
    prsn : xarray.DataArray
      Mean daily solid precipitation flux [Kg m-2 s-1] or [mm].
    tas : xarray.DataArray
      Mean daily temperature [℃] or [K]
    freq : str
      Resampling frequency

    Returns
    -------
    xarray.DataArray
      Ratio of rainfall to total precipitation during winter months (DJF)
    """
    ratio = liquid_precip_ratio(pr, prsn, tas, freq='QS-DEC')
    winter = ratio.indexes['time'].month == 12
    return ratio[winter]
