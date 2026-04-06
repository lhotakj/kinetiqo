function initActivityFilters(opts) {
    const options = opts || {};
    const onFilterChange = options.onFilterChange || function() {};

    // Use specific keys for progress page vs activities page
    // We can check if we are on activities page or progress page
    // For simplicity, let's use shared keys for now, or prefix based on page.
    // However, if we want shared filters, we use same keys.
    // The request implies reusing the control, so likely we want filters to persist across?
    // Actually, usually users expect filters to be page-specific unless specified.
    // Let's use a prefix if provided, else default.
    const storagePrefix = options.storagePrefix || 'kinetiqoActivityFilters';
    const FILTER_STORAGE_KEY = storagePrefix;
    let currentDatePreset = 'custom';

    const DYNAMIC_PRESETS = {
        'Today':          function () { return { s: moment(),                                        e: moment()                                        }; },
        'Yesterday':      function () { return { s: moment().subtract(1, 'days'),                    e: moment().subtract(1, 'days')                    }; },
        'This Week':      function () { return { s: moment().startOf('isoWeek'),                     e: moment()                                        }; },
        'Last 7 Days':    function () { return { s: moment().subtract(6, 'days'),                    e: moment()                                        }; },
        'Last 14 Days':   function () { return { s: moment().subtract(13, 'days'),                   e: moment()                                        }; },
        'This Month':     function () { return { s: moment().startOf('month'),                       e: moment()                                        }; },
        'This Year':      function () { return { s: moment().startOf('year'),                        e: moment()                                        }; },
        'Last 12 Months': function () { return { s: moment().subtract(1, 'year'),                    e: moment()                                        }; },
        'Last Week':      function () { return { s: moment().subtract(1,'week').startOf('isoWeek'),  e: moment().subtract(1,'week').endOf('isoWeek')    }; },
        'Last Month':     function () { return { s: moment().subtract(1,'month').startOf('month'),   e: moment().subtract(1,'month').endOf('month')     }; },
        'Last Year':      function () { return { s: moment().subtract(1,'year').startOf('year'),     e: moment().subtract(1,'year').endOf('year')       }; }
    };

    function loadFilters() {
        try {
            const filters = JSON.parse(localStorage.getItem(FILTER_STORAGE_KEY) || '{}');
            if (filters.types) $('#activityTypeFilter').val(filters.types);
            if (filters.search) $('#customSearch').val(filters.search);
            if (filters.datePreset) currentDatePreset = filters.datePreset;

            const presetFn = DYNAMIC_PRESETS[(currentDatePreset || '').trim()];
            if (presetFn) {
                const range = presetFn();
                filters.startDate = range.s.format('YYYY-MM-DD');
                filters.endDate   = range.e.format('YYYY-MM-DD');
            }

            if (filters.startDate) $('#startDate').val(filters.startDate);
            if (filters.endDate) $('#endDate').val(filters.endDate);
            return filters;
        } catch (e) {
            console.warn('Failed to load saved filters from localStorage:', e);
            return {};
        }
    }

    loadFilters();

    // Initialize Select2
    const $select = $('#activityTypeFilter').select2({
        placeholder: "",
        width: '100%',
        closeOnSelect: false,
        templateSelection: function (data, container) {
            if (data.id) $(container).addClass('choice-' + data.id);
            return data.text;
        }
    });

    const $container = $select.next('.select2-container').find('.select2-selection--multiple');
    if ($container.find('.select2-selection__summary').length === 0) {
        $container.prepend('<div class="select2-selection__summary"></div>');
    }

    function updateSummary() {
        const count = $('#activityTypeFilter').select2('data').length;
        const total = $('#activityTypeFilter option').length;
        let summaryText = "";
        if (count === 0) {
            summaryText = "No activities selected";
        } else if (count === total) {
            summaryText = "All activities selected (" + count + ")";
        } else {
            summaryText = count + " Activities selected";
        }
        $('.select2-selection__summary').text(summaryText);
    }

    updateSummary();

    function updateDateFilterDisplay(presetName) {
        if (presetName && presetName !== 'custom') {
            $('#dateFilter span').text(presetName);
            return;
        }
        const startDate = $('#startDate').val();
        const endDate = $('#endDate').val();
        if (startDate && endDate) {
            let startFmt = moment(startDate).format('MMM D, YYYY');
            let endFmt = moment(endDate).format('MMM D, YYYY');
            $('#dateFilter span').text(startFmt + ' - ' + endFmt);
        } else if (startDate) {
            let startFmt = moment(startDate).format('MMM D, YYYY');
            $('#dateFilter span').text('From ' + startFmt);
        } else if (endDate) {
            let endFmt = moment(endDate).format('MMM D, YYYY');
            $('#dateFilter span').text('To ' + endFmt);
        } else {
            $('#dateFilter span').text('All time');
        }
    }

    function saveFilters(presetName) {
        if (presetName !== undefined) {
            currentDatePreset = presetName;
        }

        const filters = {
            types: $('#activityTypeFilter').val(),
            startDate: $('#startDate').val(),
            endDate: $('#endDate').val(),
            search: $('#customSearch').val(),
            datePreset: currentDatePreset
        };
        localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(filters));
    }

    function initDatePicker(element) {
        const currentVal = $(element).val();
        const pickerOpts = {
            singleDatePicker: true,
            showDropdowns: true,
            autoUpdateInput: false,
            locale: {format: 'YYYY-MM-DD', cancelLabel: 'Clear'}
        };

        if (currentVal) {
            pickerOpts.startDate = currentVal;
        }

        $(element).daterangepicker(pickerOpts).on('apply.daterangepicker', function (ev, picker) {
            $(this).val(picker.startDate.format('YYYY-MM-DD'));
            updateDateFilterDisplay('custom');
            saveFilters('custom');
            onFilterChange();
        }).on('cancel.daterangepicker', function (ev, picker) {
            $(this).val('');
            updateDateFilterDisplay('custom');
            saveFilters('custom');
            onFilterChange();
        });
    }

    initDatePicker('#startDate');
    initDatePicker('#endDate');
    updateDateFilterDisplay(currentDatePreset);

    // Event Bindings
    $('#activityTypeFilter').on('change', function () {
        updateSummary();
        saveFilters();
        onFilterChange();
    });

    // Debounce search
    let searchTimeout;
    $('#customSearch').on('keyup', function () {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(function() {
            saveFilters();
            onFilterChange();
        }, 300);
    });

    $('#dateFilter').on('click', function (e) {
        e.stopPropagation();
        $('#dateFilterDropdown').toggleClass('hidden');
    });

    $(document).on('click', function (e) {
        if (!$(e.target).closest('#dateFilterDropdown').length &&
            !$(e.target).closest('#dateFilter').length &&
            !$(e.target).closest('.daterangepicker').length) {

            $('#dateFilterDropdown').addClass('hidden');
            // Guard against pages where date-pickers are not rendered (e.g. progress page)
            const dpStart = $('#startDate').data('daterangepicker');
            const dpEnd   = $('#endDate').data('daterangepicker');
            if (dpStart) dpStart.hide();
            if (dpEnd)   dpEnd.hide();
        }
    });

    $('.date-preset-btn').on('click', function () {
        const preset = $(this).data('preset');
        const presetText = $(this).text();
        let startDate, endDate;

        if (preset === 'all_time') {
            $('#startDate').val('');
            $('#endDate').val('');
        } else {
            switch (preset) {
                case 'today':
                    startDate = moment();
                    endDate = moment();
                    break;
                case 'yesterday':
                    startDate = moment().subtract(1, 'days');
                    endDate = moment().subtract(1, 'days');
                    break;
                case 'this_week':
                    startDate = moment().startOf('isoWeek');
                    endDate = moment();
                    break;
                case 'last_week':
                    startDate = moment().subtract(1, 'week').startOf('isoWeek');
                    endDate = moment().subtract(1, 'week').endOf('isoWeek');
                    break;
                case 'this_month':
                    startDate = moment().startOf('month');
                    endDate = moment();
                    break;
                case 'last_month':
                    startDate = moment().subtract(1, 'month').startOf('month');
                    endDate = moment().subtract(1, 'month').endOf('month');
                    break;
                case 'this_year':
                    startDate = moment().startOf('year');
                    endDate = moment();
                    break;
                case 'last_year':
                    startDate = moment().subtract(1, 'year').startOf('year');
                    endDate = moment().subtract(1, 'year').endOf('year');
                    break;
                case '7_days':
                    startDate = moment().subtract(6, 'days');
                    endDate = moment();
                    break;
                case '14_days':
                    startDate = moment().subtract(13, 'days');
                    endDate = moment();
                    break;
                case 'year':
                    startDate = moment().subtract(1, 'year');
                    endDate = moment();
                    break;
            }
            $('#startDate').val(startDate.format('YYYY-MM-DD'));
            $('#endDate').val(endDate.format('YYYY-MM-DD'));
        }

        initDatePicker('#startDate');
        initDatePicker('#endDate');

        $('#dateFilter span').text(presetText);
        saveFilters(presetText);
        onFilterChange();
    });

    // Select All / Deselect All buttons
    $('#selectAllBtn').click(function () {
        $('#activityTypeFilter > optgroup > option').prop('selected', true);
        $('#activityTypeFilter').trigger('change');
    });

    $('#deselectAllBtn').click(function () {
        $('#activityTypeFilter > optgroup > option').prop('selected', false);
        $('#activityTypeFilter').trigger('change');
    });
}
