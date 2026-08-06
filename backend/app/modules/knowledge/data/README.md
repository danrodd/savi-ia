# Catálogo de conocimiento

Este directorio contiene el conocimiento que SAVI carga al arrancar
(`app/main.py` → `init_catalog`). Sin él, el asistente responde sin
saber nada del ERP ni de la empresa.

> **El catálogo tiene que estar versionado.** El módulo está diseñado
> asumiendo que los archivos viajan en el repositorio y los cambios se
> aplican por deploy (ver `catalog_provider.py`).
>
> Hasta ahora no lo estaba: la regla `data/` del `.gitignore` de la raíz
> ignoraba este directorio entero, así que los `.json` nunca llegaron al
> repositorio. Ya está corregido con una excepción explícita, pero **el
> contenido real sigue faltando** — hay que copiarlo desde el equipo
> donde se mantiene y commitearlo.
>
> `installer/build.ps1` aborta si falta el directorio y advierte si no
> tiene ningún `.json`.

## Estructura esperada

```
data/
├── modules/
│   └── <module_slug>/           # debe coincidir con un valor de ModuleCode
│       ├── overview.json        # ModuleEntry           (opcional)
│       ├── forms/*.json         # FormEntry             (opcional)
│       ├── workflows/*.json     # WorkflowEntry         (opcional)
│       └── faqs/*.json          # FaqEntry              (opcional)
└── shared/
    └── glossary.json            # list[GlossaryEntry]   (opcional)
```

Todo es opcional: un directorio vacío produce un catálogo vacío y el
backend arranca igual. Lo único obligatorio es que el directorio exista.

Un `<module_slug>` que no corresponda a ningún valor de `ModuleCode`
hace fallar la carga al arrancar — es intencional, se prefiere no
levantar antes que servir respuestas con conocimiento incompleto.

## Documentación

- Estructura y semántica de cada entidad: [`backend/docs/knowledge/reference.md`](../../../../docs/knowledge/reference.md)
- Cómo editar el catálogo: [`backend/docs/knowledge/editing-guide.md`](../../../../docs/knowledge/editing-guide.md)
- Cómo agregar tipos nuevos: [`backend/docs/knowledge/extending-guide.md`](../../../../docs/knowledge/extending-guide.md)
