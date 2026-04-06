(function($) {
    $(document).ready(function() {
        var $actionsCheckbox = $('#action-toggle');
        if ($actionsCheckbox.length) {
            $actionsCheckbox.on('click', function() {
                var checked = $(this).prop('checked');
                $('.action-select').prop('checked', checked).trigger('change');
            });
        }
    });
})(django.jQuery);
