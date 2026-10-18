"""Synthetic private release contract, independent of the user's dependency catalog."""


def private_dependency():
    return {
        "id": "fixture", "kind": "package", "platforms": ["macos", "linux"],
        "groups": ["fixture"], "required_by": ["fixture"], "eligibility": "enabled-agent-machines",
        "lifecycle_doc": "dependencies/fixture.md", "requires": [],
        "contract": {
            "adapter": "package", "install_policy": "required", "update_policy": "declared-recipe",
            "recipes": {platform: {
                "manager": "ctx9-component", "package": "fixture",
                "private_catalog_url": "https://gitlab.com/api/v4/projects/1/packages/generic/fixture/1.0.0/components.json",
                "credential_binding": "ctx9-gitlab-group-read", "provenance_provider": "github",
                "provenance_project": "example/fixture",
                "provenance_workflow": ".github/workflows/publish-machine-release.yml@refs/heads/master",
            } for platform in ("macos", "linux")},
            "verify": {"command": "fixture", "args": ["--version"], "exact": "1.0.0"},
        },
    }
