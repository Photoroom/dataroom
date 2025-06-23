def theme(request):
    theme = request.COOKIES.get('theme', 'light')
    return {'theme': theme}
