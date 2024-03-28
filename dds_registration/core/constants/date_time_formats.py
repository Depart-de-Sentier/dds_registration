# Datetime formats...

# @see https://www.geeksforgeeks.org/python-strftime-function/
dateTimeFormat = "%Y.%m.%d %H:%M %Z"
dateFormat = "%B %#d, %Y"  # TODO: A day without zero? NOTE: It seems to be non-cross-platform: '%#d' is for windows and '%-d' -- for unix
#  dateFormat = '%Y.%m.%d'
dateTagFormat = "%y%m%d-%H%M"  # eg: '220208-0204'
dateTagPreciseFormat = "%y%m%d-%H%M%S"  # eg: '220208-020423'
onlyDateFormat = "%Y.%m.%d"  # eg: '2022.02.08'
shortDateFormat = "%Y.%m.%d %H:%M"  # eg: '2022.02.08-02:04'
preciseDateFormat = "%Y.%m.%d %H:%M:%S"  # eg: '2022.02.08-02:04:23'
logDateFormat = "%y%m%d-%H%M%S-%f"  # eg: '220208-020423-255157'
detailedDateFormat = "%Y.%m.%d %H:%M:%S.%f"  # eg: '2022.02.08-02:04:23.255157'


__all__ = [
    dateTimeFormat,
    dateFormat,
    dateTagFormat,
    dateTagPreciseFormat,
    shortDateFormat,
    preciseDateFormat,
    logDateFormat,
    detailedDateFormat,
]
